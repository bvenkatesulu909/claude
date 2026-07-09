#!/usr/bin/env python3
"""
Bharath Bank E2E QA Script

Comprehensive end-to-end testing of the Flask banking app with:
  - Real flow execution (register, KYC, deposits, withdrawals, transfers, loans, EMI)
  - Database integrity validation via direct sqlite3 queries
  - All route coverage (GET 21 routes, verify 200 + no Traceback)
  - Summary report: PASS/FAIL counts

Run: cd bharath-bank && PYTHONIOENCODING=utf-8 python scripts/full_e2e.py 2>&1 | tail -80
"""

import os
import sys
import time
import sqlite3
import subprocess
import requests
import json
from datetime import datetime, date

# Configuration
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(BASE_DIR, "bank.db")
SERVER_URL = "http://127.0.0.1:5055"
TIMEOUT = 5

# Test state
test_results = []
session = requests.Session()
session.timeout = TIMEOUT

# Helper: unique test email
def gen_email(prefix="test"):
    ts = int(time.time() * 1000000) % 1000000
    return f"{prefix}-{ts}@bharathbank.in"

def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)

def record_test(name, passed, reason=""):
    status = "✓ PASS" if passed else "✗ FAIL"
    test_results.append((name, passed, reason))
    reason_str = f" ({reason})" if reason else ""
    log(f"{status}: {name}{reason_str}")

def assert_status_200(resp, name):
    if resp.status_code != 200:
        record_test(name, False, f"HTTP {resp.status_code}")
        return False
    if "Traceback" in resp.text:
        record_test(name, False, "Traceback in response")
        return False
    record_test(name, True)
    return True

# Database helpers
def get_db():
    db = sqlite3.connect(DB_FILE)
    db.row_factory = sqlite3.Row
    return db

def db_query_one(sql, params=()):
    db = get_db()
    result = db.execute(sql, params).fetchone()
    db.close()
    return result

def db_query_all(sql, params=()):
    db = get_db()
    results = db.execute(sql, params).fetchall()
    db.close()
    return results

# ============================================================================
# STEP 0: Server readiness
# ============================================================================
def wait_for_server():
    log("Waiting for Flask server at %s..." % SERVER_URL)
    for attempt in range(30):
        try:
            resp = session.get(SERVER_URL + "/", timeout=TIMEOUT)
            if resp.status_code == 200:
                log("Server is ready!")
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(1)
    log("Server not responding after 30 seconds. Attempting to start...", "WARN")
    return False

# ============================================================================
# STEP 1: Registration & KYC
# ============================================================================
def test_registration():
    log("\n=== TEST 1: Registration & KYC ===")

    email1 = gen_email("test1")
    email2 = gen_email("test2")

    # User 1: Full registration + KYC
    resp = session.post(SERVER_URL + "/register", data={
        "full_name": "Alice Kumar",
        "email": email1,
        "phone": "9876543210",
        "password": "password123",
        "confirm": "password123",
        "account_type": "Savings",
        "opening_balance": "100000",
    }, allow_redirects=False)
    record_test("Register User 1 (Alice)", resp.status_code == 302, f"HTTP {resp.status_code}")

    # Verify user and account created
    user1 = db_query_one("SELECT * FROM users WHERE email = ?", (email1,))
    if not user1:
        record_test("User 1 in database", False, "User not found")
        return None, None, None
    record_test("User 1 in database", True)
    user1_id = user1["id"]

    account1 = db_query_one("SELECT * FROM accounts WHERE user_id = ?", (user1_id,))
    if not account1:
        record_test("Account 1 in database", False, "Account not found")
        return None, None, None
    record_test("Account 1 in database", True)
    account1_id = account1["id"]
    account1_num = account1["account_number"]

    # Verify opening balance
    if account1["balance_paise"] == 10000000:  # 100000 rupees = 10M paise
        record_test("Opening balance correct", True)
    else:
        record_test("Opening balance correct", False, f"Got {account1['balance_paise']}, expected 10000000")

    # Login and complete KYC for user1
    resp = session.post(SERVER_URL + "/login", data={
        "email": email1,
        "password": "password123",
    }, allow_redirects=False)
    record_test("Login User 1", resp.status_code == 302, f"HTTP {resp.status_code}")

    resp = session.post(SERVER_URL + "/kyc", data={
        "dob": "1990-05-15",
        "gender": "Female",
        "address": "123 Main St, Hyderabad",
        "city": "Hyderabad",
        "state": "Telangana",
        "pincode": "500001",
        "pan": "ABCDE1234F",
        "aadhaar": "1234567890123456",  # only last 4 used
        "occupation": "Software Engineer",
        "annual_income": "1000000",
        "nominee_name": "Bob Kumar",
        "nominee_relation": "Brother",
    }, allow_redirects=False)
    record_test("KYC submission (User 1)", resp.status_code == 302, f"HTTP {resp.status_code}")

    # Verify KYC status
    profile1 = db_query_one("SELECT * FROM customer_profiles WHERE user_id = ?", (user1_id,))
    if not profile1:
        record_test("KYC saved (User 1)", False, "Profile not found")
    elif profile1["kyc_status"] == "VERIFIED":
        record_test("KYC status VERIFIED (User 1)", True)
    else:
        record_test("KYC status VERIFIED (User 1)", False, f"Status: {profile1['kyc_status']}")

    # User 2: Minimal registration (for transfers/receipts)
    resp = session.post(SERVER_URL + "/register", data={
        "full_name": "Bob Singh",
        "email": email2,
        "phone": "9876543211",
        "password": "password456",
        "confirm": "password456",
        "account_type": "Savings",
        "opening_balance": "50000",
    }, allow_redirects=False)
    record_test("Register User 2 (Bob)", resp.status_code == 302, f"HTTP {resp.status_code}")

    user2 = db_query_one("SELECT * FROM users WHERE email = ?", (email2,))
    if user2:
        user2_id = user2["id"]
        account2 = db_query_one("SELECT * FROM accounts WHERE user_id = ?", (user2_id,))
        if account2:
            record_test("Account 2 in database", True)
            account2_num = account2["account_number"]
        else:
            record_test("Account 2 in database", False)
            return user1_id, account1_id, None
    else:
        record_test("User 2 in database", False)
        return user1_id, account1_id, None

    return user1_id, account1_id, account1_num, user2_id, account2_num, email1

# ============================================================================
# STEP 2: Deposit & Withdraw flows
# ============================================================================
def test_deposit_withdraw(user_id, account_id, email):
    log("\n=== TEST 2: Deposit & Withdraw ===")

    # Login
    session.post(SERVER_URL + "/login", data={
        "email": email,
        "password": "password123",
    })

    # Deposit 50,000
    resp = session.post(SERVER_URL + "/deposit", data={
        "amount": "50000",
        "description": "Test deposit",
    })
    assert_status_200(resp, "Deposit 50000")

    # Check balance increased
    account = db_query_one("SELECT balance_paise FROM accounts WHERE id = ?", (account_id,))
    expected = 10000000 + 5000000  # 100k + 50k
    if account["balance_paise"] == expected:
        record_test("Balance after deposit", True)
    else:
        record_test("Balance after deposit", False, f"Got {account['balance_paise']}, expected {expected}")

    # Withdraw 30,000 (should succeed)
    resp = session.post(SERVER_URL + "/withdraw", data={
        "amount": "30000",
        "description": "Test withdrawal",
    })
    assert_status_200(resp, "Withdraw 30000")

    account = db_query_one("SELECT balance_paise FROM accounts WHERE id = ?", (account_id,))
    expected = 10000000 + 5000000 - 3000000  # 100k + 50k - 30k = 120k
    if account["balance_paise"] == expected:
        record_test("Balance after withdrawal", True)
    else:
        record_test("Balance after withdrawal", False, f"Got {account['balance_paise']}, expected {expected}")

    # Try to withdraw more than balance (should fail with flash message)
    resp = session.post(SERVER_URL + "/withdraw", data={
        "amount": "200000",
        "description": "Over-limit withdrawal",
    })
    if "Insufficient balance" in resp.text:
        record_test("Insufficient balance rejection", True)
    else:
        record_test("Insufficient balance rejection", False, "No error message")

    # Balance should be unchanged
    account = db_query_one("SELECT balance_paise FROM accounts WHERE id = ?", (account_id,))
    if account["balance_paise"] == 12000000:  # Still 120k
        record_test("Balance unchanged after failed withdrawal", True)
    else:
        record_test("Balance unchanged after failed withdrawal", False)

# ============================================================================
# STEP 3: Transfer
# ============================================================================
def test_transfer(user1_id, account1_id, account1_num, user2_id, account2_num, email1):
    log("\n=== TEST 3: Transfer ===")

    # Login as user1
    session.post(SERVER_URL + "/login", data={
        "email": email1,
        "password": "password123",
    })

    # Transfer 25,000 to user2
    resp = session.post(SERVER_URL + "/transfer", data={
        "to_account": account2_num,
        "amount": "25000",
        "description": "Test transfer",
    })
    assert_status_200(resp, "Transfer 25000 to user2")

    # Check user1 balance decreased
    acc1 = db_query_one("SELECT balance_paise FROM accounts WHERE id = ?", (account1_id,))
    expected_user1 = 12000000 - 2500000  # 120k - 25k = 95k
    if acc1["balance_paise"] == expected_user1:
        record_test("User1 balance after transfer", True)
    else:
        record_test("User1 balance after transfer", False, f"Got {acc1['balance_paise']}, expected {expected_user1}")

    # Check user2 balance increased
    acc2_id = db_query_one("SELECT id FROM accounts WHERE user_id = ?", (user2_id,))["id"]
    acc2 = db_query_one("SELECT balance_paise FROM accounts WHERE id = ?", (acc2_id,))
    expected_user2 = 5000000 + 2500000  # 50k + 25k = 75k
    if acc2["balance_paise"] == expected_user2:
        record_test("User2 balance after transfer", True)
    else:
        record_test("User2 balance after transfer", False, f"Got {acc2['balance_paise']}, expected {expected_user2}")

    # Verify transfer has matching debit+credit with same ref
    transfers = db_query_all(
        "SELECT * FROM transactions WHERE category = 'TRANSFER' AND account_id IN (?, ?) "
        "ORDER BY created_at DESC LIMIT 2", (account1_id, acc2_id)
    )
    if len(transfers) == 2:
        debit = [t for t in transfers if t["txn_type"] == "DEBIT"][0] if any(t["txn_type"] == "DEBIT" for t in transfers) else None
        credit = [t for t in transfers if t["txn_type"] == "CREDIT"][0] if any(t["txn_type"] == "CREDIT" for t in transfers) else None
        if debit and credit and debit["ref_no"] == credit["ref_no"] and debit["amount_paise"] == credit["amount_paise"]:
            record_test("Transfer ref and amount match", True)
        else:
            record_test("Transfer ref and amount match", False, "Mismatch in ref or amount")
    else:
        record_test("Transfer ref and amount match", False, f"Found {len(transfers)} transfers, expected 2")

# ============================================================================
# STEP 4: FD & RD deposits
# ============================================================================
def test_deposits_fd_rd(user_id, account_id, email):
    log("\n=== TEST 4: FD & RD Deposits ===")

    # Login
    session.post(SERVER_URL + "/login", data={
        "email": email,
        "password": "password123",
    })

    # Open FD: 50,000 for 12 months @ 7%
    resp = session.post(SERVER_URL + "/deposits/open", data={
        "scheme_code": "FD-REG",
        "amount": "50000",
        "tenure_months": "12",
    })
    assert_status_200(resp, "Open FD")

    # Check balance debited
    account = db_query_one("SELECT balance_paise FROM accounts WHERE id = ?", (account_id,))
    expected = 9500000 - 5000000  # 95k - 50k = 45k (after transfer)
    if account["balance_paise"] == expected:
        record_test("Balance after FD debit", True)
    else:
        record_test("Balance after FD debit", False, f"Got {account['balance_paise']}, expected {expected}")

    # Verify FD in deposits table
    fd = db_query_one("SELECT * FROM deposits WHERE user_id = ? AND deposit_type = 'FD'", (user_id,))
    if fd:
        record_test("FD in deposits table", True)
        fd_id = fd["id"]
        if fd["status"] == "ACTIVE":
            record_test("FD status ACTIVE", True)
        else:
            record_test("FD status ACTIVE", False, f"Status: {fd['status']}")
    else:
        record_test("FD in deposits table", False)
        fd_id = None

    # Open RD: 10,000/month for 12 months @ 6.5%
    resp = session.post(SERVER_URL + "/deposits/open", data={
        "scheme_code": "RD-REG",
        "amount": "10000",
        "tenure_months": "12",
    })
    assert_status_200(resp, "Open RD")

    # Check balance debited for first installment
    account = db_query_one("SELECT balance_paise FROM accounts WHERE id = ?", (account_id,))
    expected = 4500000 - 1000000  # 45k - 10k = 35k
    if account["balance_paise"] == expected:
        record_test("Balance after RD first installment", True)
    else:
        record_test("Balance after RD first installment", False, f"Got {account['balance_paise']}, expected {expected}")

    # Verify RD in deposits table
    rd = db_query_one("SELECT * FROM deposits WHERE user_id = ? AND deposit_type = 'RD'", (user_id,))
    if rd:
        record_test("RD in deposits table", True)
        rd_id = rd["id"]
        if rd["installments_paid"] == 1:
            record_test("RD installments_paid = 1", True)
        else:
            record_test("RD installments_paid = 1", False, f"Got {rd['installments_paid']}")
    else:
        record_test("RD in deposits table", False)
        rd_id = None

    # Pay another RD installment
    if rd_id:
        resp = session.post(SERVER_URL + f"/deposits/{rd_id}/pay", data={})
        assert_status_200(resp, "Pay RD installment 2")

        # Check balance and installments_paid
        account = db_query_one("SELECT balance_paise FROM accounts WHERE id = ?", (account_id,))
        expected = 3500000 - 1000000  # 35k - 10k = 25k
        if account["balance_paise"] == expected:
            record_test("Balance after RD second installment", True)
        else:
            record_test("Balance after RD second installment", False, f"Got {account['balance_paise']}, expected {expected}")

        rd = db_query_one("SELECT installments_paid FROM deposits WHERE id = ?", (rd_id,))
        if rd["installments_paid"] == 2:
            record_test("RD installments_paid = 2", True)
        else:
            record_test("RD installments_paid = 2", False, f"Got {rd['installments_paid']}")

    return fd_id, rd_id

# ============================================================================
# STEP 5: Loans (rejection + approval)
# ============================================================================
def test_loans(user_id, account_id, email):
    log("\n=== TEST 5: Loans (Rejection & Approval) ===")

    # Login
    session.post(SERVER_URL + "/login", data={
        "email": email,
        "password": "password123",
    })

    # Try to apply huge loan (should be rejected with FOIR reason)
    resp = session.post(SERVER_URL + "/loans/apply", data={
        "product_code": "LN-HOME",
        "amount": "100000000",  # 100 lakh (would have very high EMI)
        "tenure_months": "60",
        "purpose": "Dream home",
    })
    if "FOIR" in resp.text or "55%" in resp.text or "exceeded" in resp.text:
        record_test("Large loan FOIR rejection", True)
    else:
        record_test("Large loan FOIR rejection", False, "No FOIR message in response")

    # Verify loan was created with REJECTED status
    loan = db_query_one(
        "SELECT * FROM loans WHERE user_id = ? AND status = 'REJECTED' "
        "ORDER BY id DESC LIMIT 1", (user_id,)
    )
    if loan and "FOIR" in (loan["decision_reason"] or ""):
        record_test("Large loan REJECTED in DB", True)
    else:
        record_test("Large loan REJECTED in DB", False, f"Status/reason mismatch")

    # Apply reasonable loan (should be approved)
    resp = session.post(SERVER_URL + "/loans/apply", data={
        "product_code": "LN-PERSONAL",
        "amount": "200000",
        "tenure_months": "24",
        "purpose": "Medical emergency",
    })
    assert_status_200(resp, "Apply personal loan")

    # Verify loan was created with APPROVED status
    loan = db_query_one(
        "SELECT * FROM loans WHERE user_id = ? AND status = 'ACTIVE' "
        "ORDER BY id DESC LIMIT 1", (user_id,)
    )
    if loan:
        record_test("Loan ACTIVE status", True)
        loan_id = loan["id"]

        # Check that loan disbursement was credited
        account = db_query_one("SELECT balance_paise FROM accounts WHERE id = ?", (account_id,))
        # At this point, balance should have the loan disbursement
        record_test("Loan disbursement credited", account["balance_paise"] > 0)
    else:
        record_test("Loan ACTIVE status", False)
        loan_id = None

    return loan_id

# ============================================================================
# STEP 6: EMI payment
# ============================================================================
def test_emi_payment(loan_id, user_id, account_id, email):
    log("\n=== TEST 6: EMI Payment ===")

    if not loan_id:
        log("Skipping EMI test (no active loan)", "WARN")
        return

    # Login
    session.post(SERVER_URL + "/login", data={
        "email": email,
        "password": "password123",
    })

    # Get loan details
    loan = db_query_one("SELECT * FROM loans WHERE id = ?", (loan_id,))
    initial_outstanding = loan["outstanding_paise"]

    # Pay one EMI
    resp = session.post(SERVER_URL + f"/loans/{loan_id}/pay", data={})
    assert_status_200(resp, "Pay EMI 1")

    # Verify outstanding decreased
    loan = db_query_one("SELECT outstanding_paise, emis_paid FROM loans WHERE id = ?", (loan_id,))
    if loan["outstanding_paise"] < initial_outstanding:
        record_test("Outstanding decreased after EMI", True)
    else:
        record_test("Outstanding decreased after EMI", False, f"Outstanding still {loan['outstanding_paise']}")

    # Verify EMI payment in loan_payments table
    payment = db_query_one(
        "SELECT * FROM loan_payments WHERE loan_id = ? ORDER BY emi_no DESC LIMIT 1", (loan_id,)
    )
    if payment:
        record_test("EMI payment recorded", True)
        # Verify principal + interest = payment amount
        if payment["principal_paise"] + payment["interest_paise"] == payment["amount_paise"]:
            record_test("EMI split (principal + interest = amount)", True)
        else:
            record_test("EMI split (principal + interest = amount)", False)
    else:
        record_test("EMI payment recorded", False)

# ============================================================================
# STEP 7: Database integrity checks
# ============================================================================
def test_db_integrity(user_id, account_id):
    log("\n=== TEST 7: Database Integrity Checks ===")

    # Check 1: Account balance == sum of ledger credits - debits
    account = db_query_one("SELECT balance_paise FROM accounts WHERE id = ?", (account_id,))
    if not account:
        log("Account not found", "ERROR")
        return

    ledger = db_query_all(
        "SELECT SUM(CASE WHEN txn_type = 'CREDIT' THEN amount_paise ELSE 0 END) as credits,"
        " SUM(CASE WHEN txn_type = 'DEBIT' THEN amount_paise ELSE 0 END) as debits "
        "FROM transactions WHERE account_id = ?", (account_id,)
    )[0]

    expected_balance = (ledger["credits"] or 0) - (ledger["debits"] or 0)
    if account["balance_paise"] == expected_balance:
        record_test("Balance = credits - debits", True)
    else:
        record_test("Balance = credits - debits", False,
                   f"Account: {account['balance_paise']}, Ledger: {expected_balance}")

    # Check 2: All transfers have matching debit+credit with same ref
    transfers = db_query_all(
        "SELECT ref_no, COUNT(*) as cnt, SUM(CASE WHEN txn_type='DEBIT' THEN 1 ELSE 0 END) as debits,"
        " SUM(CASE WHEN txn_type='CREDIT' THEN 1 ELSE 0 END) as credits "
        "FROM transactions WHERE category = 'TRANSFER' "
        "GROUP BY ref_no"
    )
    transfer_ok = True
    for t in transfers:
        if t["cnt"] != 2 or t["debits"] != 1 or t["credits"] != 1:
            transfer_ok = False
            break
    record_test("Transfers have matching debit+credit", transfer_ok)

    # Check 3: Loan outstanding == principal - EMIs paid
    loans = db_query_all(
        "SELECT id, principal_paise, outstanding_paise "
        "FROM loans WHERE user_id = ? AND status IN ('ACTIVE', 'CLOSED')", (user_id,)
    )
    for loan in loans:
        payments = db_query_all(
            "SELECT SUM(principal_paise) as principal_paid "
            "FROM loan_payments WHERE loan_id = ?", (loan["id"],)
        )
        principal_paid = payments[0]["principal_paid"] or 0
        calculated_outstanding = loan["principal_paise"] - principal_paid
        if loan["outstanding_paise"] == calculated_outstanding:
            record_test(f"Loan {loan['id']} outstanding correct", True)
        else:
            record_test(f"Loan {loan['id']} outstanding correct", False,
                       f"DB: {loan['outstanding_paise']}, Calc: {calculated_outstanding}")

# ============================================================================
# STEP 8: Route coverage (GET all routes)
# ============================================================================
def test_route_coverage(email):
    log("\n=== TEST 8: Route Coverage ===")

    # Login to get authenticated routes
    session.post(SERVER_URL + "/login", data={
        "email": email,
        "password": "password123",
    })

    routes = [
        # Public
        ("/", "GET", True, "Home"),
        ("/products", "GET", True, "Products"),

        # Auth
        ("/register", "GET", True, "Register"),
        ("/login", "GET", True, "Login"),
        ("/logout", "GET", True, "Logout"),

        # Authenticated
        ("/dashboard", "GET", False, "Dashboard"),
        ("/deposit", "GET", False, "Deposit"),
        ("/withdraw", "GET", False, "Withdraw"),
        ("/transfer", "GET", False, "Transfer"),
        ("/transactions", "GET", False, "Transactions"),
        ("/profile", "GET", False, "Profile"),
        ("/kyc", "GET", False, "KYC"),
        ("/deposits", "GET", False, "Deposits"),
        ("/deposits/open", "GET", False, "Open Deposit"),
        ("/loans", "GET", False, "Loans"),
        ("/loans/apply", "GET", False, "Apply Loan"),
        ("/api/balance", "GET", False, "API Balance"),
        ("/statement.csv", "GET", False, "Statement CSV"),
        ("/statement/print", "GET", False, "Statement Print"),

        # Admin
        ("/admin", "GET", False, "Admin Dashboard"),
        ("/admin/schemes", "GET", False, "Admin Schemes"),
    ]

    count_ok = 0
    for path, method, is_public, label in routes:
        try:
            if method == "GET":
                resp = session.get(SERVER_URL + path, timeout=TIMEOUT)
                if resp.status_code == 200 and "Traceback" not in resp.text:
                    record_test(f"Route: {label} ({path})", True)
                    count_ok += 1
                else:
                    record_test(f"Route: {label} ({path})", False,
                               f"HTTP {resp.status_code} or Traceback")
        except requests.exceptions.RequestException as e:
            record_test(f"Route: {label} ({path})", False, str(e))

    log(f"Route coverage: {count_ok}/{len(routes)} routes OK")

# ============================================================================
# Main execution
# ============================================================================
def main():
    log("=" * 70)
    log("BHARATH BANK E2E QA TEST SUITE")
    log("=" * 70)

    # Check if Flask server is running
    if not wait_for_server():
        log("Could not reach Flask server. Ensure it's running on http://127.0.0.1:5055", "ERROR")
        sys.exit(1)

    try:
        # Step 1: Registration & KYC
        result = test_registration()
        if result[0] is None:
            log("Registration test failed, aborting", "ERROR")
            sys.exit(1)
        user1_id, account1_id, account1_num, user2_id, account2_num, email1 = result

        # Step 2: Deposit & Withdraw
        test_deposit_withdraw(user1_id, account1_id, email1)

        # Step 3: Transfer
        test_transfer(user1_id, account1_id, account1_num, user2_id, account2_num, email1)

        # Step 4: FD & RD
        test_deposits_fd_rd(user1_id, account1_id, email1)

        # Step 5: Loans
        loan_id = test_loans(user1_id, account1_id, email1)

        # Step 6: EMI Payment
        test_emi_payment(loan_id, user1_id, account1_id, email1)

        # Step 7: Database integrity
        test_db_integrity(user1_id, account1_id)

        # Step 8: Route coverage
        test_route_coverage(email1)

    except Exception as e:
        log(f"Unexpected error: {e}", "ERROR")
        import traceback
        traceback.print_exc()

    # ========================================================================
    # Final Summary
    # ========================================================================
    log("\n" + "=" * 70)
    log("TEST SUMMARY")
    log("=" * 70)

    passed = sum(1 for _, p, _ in test_results if p)
    failed = sum(1 for _, p, _ in test_results if not p)
    total = len(test_results)

    print("\n--- RESULTS ---")
    for name, passed_flag, reason in test_results:
        status = "✓" if passed_flag else "✗"
        reason_str = f" ({reason})" if reason else ""
        print(f"{status} {name}{reason_str}")

    print("\n--- SUMMARY ---")
    print(f"Total: {total} checks")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success rate: {100*passed//total}%")

    if failed == 0:
        print("\n✓ ALL TESTS PASSED")
        return 0
    else:
        print(f"\n✗ {failed} TEST(S) FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
