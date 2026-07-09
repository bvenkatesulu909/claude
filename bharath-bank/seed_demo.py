"""
Demo-data seeding script for Bharath Bank of India.

Populates bank.db with a handful of realistic demo customers — savings
accounts, KYC profiles, term deposits (FD/RD), and an active loan — so the
app has something to look at without manually clicking through the UI.

This script talks to SQLite directly with a plain sqlite3 connection (no
Flask request/app context is available outside of a running server), and
replicates the same minimal INSERT logic that app.py's request handlers use
(see gen_account_number / gen_loan_account / _post_transaction in app.py).
It imports `finance` for the interest/EMI maths and werkzeug for password
hashing, matching the real app exactly.

Safe to re-run: existing demo users (matched by e-mail) are removed and
recreated each time, so the script is idempotent. It never touches
non-demo users, and never drops any tables.

Usage:
    cd bharath-bank
    python seed_demo.py
"""

import os
import random
import sqlite3
from datetime import date, datetime

from werkzeug.security import generate_password_hash

import finance

# Reuse the real app's schema/bootstrap so this script never drifts from
# the live schema. init_db() is idempotent (CREATE TABLE IF NOT EXISTS +
# seed_reference_data only inserts schemes/loan_products if empty).
import app as bank_app

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "bank.db")

IFSC_CODE = bank_app.IFSC_CODE
DEMO_PASSWORD = "demo123"

# --------------------------------------------------------------------------- #
# Demo customer definitions
# --------------------------------------------------------------------------- #
DEMO_CUSTOMERS = [
    {
        "full_name": "Aarav Sharma",
        "email": "aarav.sharma@demo.bharathbank.in",
        "phone": "9876500001",
        "opening_paise": 6_50000_00,   # Rs. 6,50,000.00 (covers the FD below)
        "profile": {
            "dob": "1990-04-12", "gender": "Male",
            "address": "12-3 Jubilee Hills Road No. 4", "city": "Hyderabad",
            "state": "Telangana", "pincode": "500033", "pan": "AAAPS1234A",
            "aadhaar_last4": "1234", "occupation": "Software Engineer",
            "annual_income_paise": 12_00000_00,   # Rs. 12,00,000/yr
            "nominee_name": "Meera Sharma", "nominee_relation": "Spouse",
        },
        "fd": {"scheme_code": "FD-REG", "amount_paise": 5_00000_00, "tenure_months": 12},
    },
    {
        "full_name": "Diya Patel",
        "email": "diya.patel@demo.bharathbank.in",
        "phone": "9876500002",
        "opening_paise": 18_50000,     # Rs. 18,500.00
        "profile": {
            "dob": "1994-09-21", "gender": "Female",
            "address": "45 Satellite Road", "city": "Ahmedabad",
            "state": "Gujarat", "pincode": "380015", "pan": "AAAPP5678B",
            "aadhaar_last4": "5678", "occupation": "Chartered Accountant",
            "annual_income_paise": 9_50000_00,     # Rs. 9,50,000/yr
            "nominee_name": "Raj Patel", "nominee_relation": "Father",
        },
        "rd": {"scheme_code": "RD-REG", "amount_paise": 5000_00, "tenure_months": 24},
    },
    {
        "full_name": "Rohan Mehta",
        "email": "rohan.mehta@demo.bharathbank.in",
        "phone": "9876500003",
        "opening_paise": 60000,        # Rs. 600.00
        "profile": {
            "dob": "1988-01-30", "gender": "Male",
            "address": "7 MG Road", "city": "Pune",
            "state": "Maharashtra", "pincode": "411001", "pan": "AAAPM4321C",
            "aadhaar_last4": "4321", "occupation": "Small Business Owner",
            "annual_income_paise": 7_20000_00,     # Rs. 7,20,000/yr
            "nominee_name": "Sunita Mehta", "nominee_relation": "Mother",
        },
        "loan": {
            "product_code": "LN-PERSONAL", "amount_paise": 3_00000_00,
            "tenure_months": 24, "purpose": "Home renovation", "paid_emis": 3,
        },
    },
    {
        "full_name": "Ananya Reddy",
        "email": "ananya.reddy@demo.bharathbank.in",
        "phone": "9876500004",
        "opening_paise": 1_20000_00,   # Rs. 1,20,000.00
        "profile": {
            "dob": "1996-11-05", "gender": "Female",
            "address": "22 Banjara Hills", "city": "Hyderabad",
            "state": "Telangana", "pincode": "500034", "pan": "AAAPR8765D",
            "aadhaar_last4": "8765", "occupation": "Doctor",
            "annual_income_paise": 15_00000_00,    # Rs. 15,00,000/yr
            "nominee_name": "Kiran Reddy", "nominee_relation": "Sibling",
        },
    },
]


# --------------------------------------------------------------------------- #
# Small local helpers (standalone equivalents of the app.py/flask.g versions)
# --------------------------------------------------------------------------- #
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def gen_ref_no():
    return "BBI" + datetime.now().strftime("%y%m%d") + "".join(
        str(random.randint(0, 9)) for _ in range(6)
    )


def gen_account_number(db):
    """Unique 12-digit account number, branch-prefixed (matches app.gen_account_number)."""
    while True:
        number = "1729" + "".join(str(random.randint(0, 9)) for _ in range(8))
        if not db.execute(
            "SELECT 1 FROM accounts WHERE account_number = ?", (number,)
        ).fetchone():
            return number


def gen_loan_account(db):
    """Unique loan account number (matches app.gen_loan_account)."""
    while True:
        number = "BBILN" + "".join(str(random.randint(0, 9)) for _ in range(8))
        if not db.execute(
            "SELECT 1 FROM loans WHERE loan_account = ?", (number,)
        ).fetchone():
            return number


def post_transaction(db, account_id, txn_type, amount_paise, category, description,
                      counterparty, ref=None):
    """Standalone equivalent of app._post_transaction — updates balance_paise and
    inserts the matching ledger row, keeping a running balance so
    transactions.balance_paise always equals accounts.balance_paise after the txn.
    """
    row = db.execute(
        "SELECT balance_paise FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()
    balance = row[0]
    balance = balance + amount_paise if txn_type == "CREDIT" else balance - amount_paise

    db.execute("UPDATE accounts SET balance_paise = ? WHERE id = ?", (balance, account_id))
    db.execute(
        "INSERT INTO transactions (account_id, txn_type, amount_paise, balance_paise,"
        " category, description, counterparty, ref_no, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (account_id, txn_type, amount_paise, balance, category, description,
         counterparty, ref or gen_ref_no(), now_str()),
    )
    return balance


def delete_existing_demo_users(db):
    """Idempotency: wipe any previous run's demo rows (matched by e-mail) before
    recreating them, cascading through accounts/transactions/deposits/loans/etc.
    Only ever touches rows tied to the demo e-mail addresses below — never
    touches any other user.
    """
    emails = [c["email"] for c in DEMO_CUSTOMERS]
    placeholders = ",".join("?" * len(emails))
    user_ids = [r[0] for r in db.execute(
        f"SELECT id FROM users WHERE email IN ({placeholders})", emails
    ).fetchall()]
    if not user_ids:
        return
    uid_placeholders = ",".join("?" * len(user_ids))

    account_ids = [r[0] for r in db.execute(
        f"SELECT id FROM accounts WHERE user_id IN ({uid_placeholders})", user_ids
    ).fetchall()]
    if account_ids:
        acc_placeholders = ",".join("?" * len(account_ids))
        db.execute(f"DELETE FROM transactions WHERE account_id IN ({acc_placeholders})", account_ids)

    loan_ids = [r[0] for r in db.execute(
        f"SELECT id FROM loans WHERE user_id IN ({uid_placeholders})", user_ids
    ).fetchall()]
    if loan_ids:
        loan_placeholders = ",".join("?" * len(loan_ids))
        db.execute(f"DELETE FROM loan_payments WHERE loan_id IN ({loan_placeholders})", loan_ids)

    db.execute(f"DELETE FROM loans WHERE user_id IN ({uid_placeholders})", user_ids)
    db.execute(f"DELETE FROM deposits WHERE user_id IN ({uid_placeholders})", user_ids)
    db.execute(f"DELETE FROM customer_profiles WHERE user_id IN ({uid_placeholders})", user_ids)
    db.execute(f"DELETE FROM accounts WHERE user_id IN ({uid_placeholders})", user_ids)
    db.execute(f"DELETE FROM users WHERE id IN ({uid_placeholders})", user_ids)
    db.commit()


# --------------------------------------------------------------------------- #
# Main seeding routine
# --------------------------------------------------------------------------- #
def seed():
    # Ensure schema + reference data (schemes / loan_products) exist. This is
    # exactly what app.py does on startup — safe & idempotent (CREATE TABLE IF
    # NOT EXISTS, and seed_reference_data only inserts when the tables are empty).
    bank_app.init_db()

    db = sqlite3.connect(DB_FILE)
    db.execute("PRAGMA foreign_keys = ON")

    delete_existing_demo_users(db)

    summary_rows = []

    for cust in DEMO_CUSTOMERS:
        created = now_str()

        # --- user ---------------------------------------------------------
        cur = db.execute(
            "INSERT INTO users (full_name, email, phone, password_hash, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (cust["full_name"], cust["email"], cust["phone"],
             generate_password_hash(DEMO_PASSWORD), created),
        )
        user_id = cur.lastrowid

        # --- savings account + opening deposit ----------------------------
        acc_number = gen_account_number(db)
        acc_cur = db.execute(
            "INSERT INTO accounts (user_id, account_number, account_type, ifsc,"
            " balance_paise, status, created_at) VALUES (?, ?, 'Savings', ?, 0, 'ACTIVE', ?)",
            (user_id, acc_number, IFSC_CODE, created),
        )
        account_id = acc_cur.lastrowid

        opening_paise = cust["opening_paise"]
        post_transaction(db, account_id, "CREDIT", opening_paise, "DEPOSIT",
                          "Opening deposit", "Self")

        # --- KYC profile (complete -> VERIFIED) ----------------------------
        p = cust["profile"]
        db.execute(
            "INSERT INTO customer_profiles (user_id, dob, gender, address, city, state,"
            " pincode, pan, aadhaar_last4, occupation, annual_income_paise, nominee_name,"
            " nominee_relation, kyc_status, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'VERIFIED', ?)",
            (user_id, p["dob"], p["gender"], p["address"], p["city"], p["state"],
             p["pincode"], p["pan"], p["aadhaar_last4"], p["occupation"],
             p["annual_income_paise"], p["nominee_name"], p["nominee_relation"], created),
        )

        # --- optional Fixed Deposit ----------------------------------------
        if "fd" in cust:
            fd = cust["fd"]
            scheme = db.execute(
                "SELECT * FROM schemes WHERE code = ?", (fd["scheme_code"],)
            ).fetchone()
            rate = scheme[3]        # interest_rate column
            scheme_name = scheme[1]
            amount = fd["amount_paise"]
            tenure = fd["tenure_months"]
            maturity = finance.fd_maturity_paise(amount, rate, tenure)
            total_invested = amount
            interest = maturity - total_invested
            start = date.today()
            maturity_date = finance.add_months(start, tenure).isoformat()
            ref = gen_ref_no()

            post_transaction(db, account_id, "DEBIT", amount, "FD",
                              f"{scheme_name} (FD) opened", "Deposit", ref=ref)
            db.execute(
                "INSERT INTO deposits (user_id, deposit_type, scheme_code, scheme_name,"
                " principal_paise, interest_rate, tenure_months, maturity_paise,"
                " total_invested_paise, interest_paise, installments_paid, start_date,"
                " maturity_date, status, ref_no)"
                " VALUES (?, 'FD', ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 'ACTIVE', ?)",
                (user_id, fd["scheme_code"], scheme_name, amount, rate, tenure,
                 maturity, total_invested, interest, start.isoformat(), maturity_date, ref),
            )

        # --- optional Recurring Deposit -------------------------------------
        if "rd" in cust:
            rd = cust["rd"]
            scheme = db.execute(
                "SELECT * FROM schemes WHERE code = ?", (rd["scheme_code"],)
            ).fetchone()
            rate = scheme[3]
            scheme_name = scheme[1]
            installment = rd["amount_paise"]
            tenure = rd["tenure_months"]
            maturity = finance.rd_maturity_paise(installment, rate, tenure)
            total_invested = installment * tenure
            interest = maturity - total_invested
            installments_paid = 1          # first installment debited now, like open_deposit()
            start = date.today()
            maturity_date = finance.add_months(start, tenure).isoformat()
            ref = gen_ref_no()

            post_transaction(db, account_id, "DEBIT", installment, "RD",
                              f"{scheme_name} (RD) opened", "Deposit", ref=ref)
            db.execute(
                "INSERT INTO deposits (user_id, deposit_type, scheme_code, scheme_name,"
                " principal_paise, interest_rate, tenure_months, maturity_paise,"
                " total_invested_paise, interest_paise, installments_paid, start_date,"
                " maturity_date, status, ref_no)"
                " VALUES (?, 'RD', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?)",
                (user_id, rd["scheme_code"], scheme_name, installment, rate, tenure,
                 maturity, total_invested, interest, installments_paid,
                 start.isoformat(), maturity_date, ref),
            )

        # --- optional active Loan --------------------------------------------
        if "loan" in cust:
            ln = cust["loan"]
            product = db.execute(
                "SELECT * FROM loan_products WHERE code = ?", (ln["product_code"],)
            ).fetchone()
            product_name = product[1]
            rate = product[2]
            processing_fee_pct = product[6]
            amount = ln["amount_paise"]
            tenure = ln["tenure_months"]

            emi, total_payable, total_interest = finance.loan_totals(amount, rate, tenure)
            loan_account = gen_loan_account(db)
            ref = gen_ref_no()
            applied_at = now_str()

            # Disbursement credit + processing fee debit (mirrors apply_loan()).
            post_transaction(db, account_id, "CREDIT", amount, "LOAN",
                              f"{product_name} disbursed ({loan_account})", "Loan", ref=ref)
            fee = round(amount * processing_fee_pct / 100)
            if fee > 0:
                post_transaction(db, account_id, "DEBIT", fee, "LOAN",
                                  f"{product_name} processing fee ({loan_account})",
                                  "Loan", ref=gen_ref_no())

            loan_cur = db.execute(
                "INSERT INTO loans (user_id, product_code, product_name, loan_account,"
                " principal_paise, interest_rate, tenure_months, emi_paise,"
                " total_payable_paise, total_interest_paise, outstanding_paise, emis_paid,"
                " status, decision_reason, purpose, applied_at, decided_at, ref_no)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'ACTIVE', ?, ?, ?, ?, ?)",
                (user_id, ln["product_code"], product_name, loan_account, amount, rate,
                 tenure, emi, total_payable, total_interest, amount,
                 "Approved instantly based on income and eligibility.",
                 ln.get("purpose", ""), applied_at, applied_at, ref),
            )
            loan_id = loan_cur.lastrowid

            # Pay a few EMIs so the loan looks "in progress" rather than brand new.
            outstanding = amount
            emis_paid = 0
            for k in range(ln.get("paid_emis", 0)):
                interest_amt, principal_amt, pay, new_out = finance.emi_split(
                    outstanding, rate, emi)
                pay_ref = gen_ref_no()
                post_transaction(db, account_id, "DEBIT", pay, "LOAN",
                                  f"{product_name} EMI ({loan_account})", "Loan", ref=pay_ref)
                emis_paid += 1
                db.execute(
                    "INSERT INTO loan_payments (loan_id, emi_no, amount_paise, principal_paise,"
                    " interest_paise, outstanding_paise, paid_at, ref_no)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (loan_id, emis_paid, pay, principal_amt, interest_amt, new_out,
                     now_str(), pay_ref),
                )
                outstanding = new_out

            new_status = "CLOSED" if outstanding <= 0 else "ACTIVE"
            db.execute(
                "UPDATE loans SET outstanding_paise = ?, emis_paid = ?, status = ? WHERE id = ?",
                (outstanding, emis_paid, new_status, loan_id),
            )

        db.commit()

        final_balance = db.execute(
            "SELECT balance_paise FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()[0]
        summary_rows.append({
            "name": cust["full_name"],
            "email": cust["email"],
            "account_number": acc_number,
            "balance_paise": final_balance,
        })

    # --------------------------------------------------------------------- #
    # Reconciliation check: every demo account's balance_paise must equal
    # the sum of its ledger (credits - debits).
    # --------------------------------------------------------------------- #
    print("\nReconciliation check (balance_paise vs. ledger sum):")
    all_ok = True
    for row in summary_rows:
        acc = db.execute(
            "SELECT id, balance_paise FROM accounts WHERE account_number = ?",
            (row["account_number"],),
        ).fetchone()
        acc_id, stored_balance = acc[0], acc[1]
        ledger_sum = db.execute(
            "SELECT COALESCE(SUM(CASE WHEN txn_type = 'CREDIT' THEN amount_paise"
            " ELSE -amount_paise END), 0) FROM transactions WHERE account_id = ?",
            (acc_id,),
        ).fetchone()[0]
        ok = (stored_balance == ledger_sum)
        all_ok = all_ok and ok
        status = "OK" if ok else "MISMATCH"
        print(f"  {row['email']:<38} stored={stored_balance:>12} "
              f"ledger={ledger_sum:>12}  [{status}]")
    if not all_ok:
        raise SystemExit("Reconciliation FAILED — a demo account's balance does not "
                          "match its transaction ledger.")

    db.close()
    return summary_rows


def print_summary(rows):
    print("\n" + "=" * 78)
    print(f"  Bharath Bank of India — demo data seeded ({len(rows)} customers)")
    print("  Password for all demo accounts: " + DEMO_PASSWORD)
    print("=" * 78)
    header = f"{'Name':<16} {'Email':<38} {'Account No.':<14} {'Balance (Rs.)':>14}"
    print(header)
    print("-" * len(header))
    for row in rows:
        balance_rupees = row["balance_paise"] / 100
        print(f"{row['name']:<16} {row['email']:<38} {row['account_number']:<14} "
              f"{balance_rupees:>14,.2f}")
    print("=" * 78)


if __name__ == "__main__":
    rows = seed()
    print_summary(rows)
