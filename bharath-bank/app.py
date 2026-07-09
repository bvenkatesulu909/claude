"""
Bharath Bank of India — a full-stack (dummy) internet banking application.

Backend : Flask + SQLite (standard library sqlite3, no ORM)
Security: werkzeug password hashing + server-side sessions
Money   : stored internally as INTEGER paise to avoid float rounding errors

This is a demonstration / educational app. It is NOT connected to any real
banking network and holds no real money.
"""

import os
import re
import hmac
import math
import random
import secrets
import sqlite3
import functools
from datetime import datetime, date

from flask import (
    Flask, g, render_template, request, redirect, url_for,
    session, flash, jsonify, abort, Response, current_app,
)
from markupsafe import Markup
from werkzeug.security import generate_password_hash, check_password_hash

import finance
from statement_export import statement_rows, to_csv, to_printable_html

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "bank.db")

BANK_NAME = "Bharath Bank of India"
BANK_SHORT = "BBI"
IFSC_CODE = "BBIN0001729"          # single-branch demo bank
BRANCH_NAME = "Bharath Nagar Main Branch, Hyderabad"

app = Flask(__name__)

# --- Secret key: fail closed in production, dev fallback otherwise (SECURITY C1) ---
_secret = os.environ.get("BBI_SECRET")
if not _secret:
    if os.environ.get("BBI_ENV") == "production":
        raise RuntimeError("BBI_SECRET must be set in production.")
    _secret = "bharath-bank-dev-secret-change-me"   # dev-only convenience
app.config["SECRET_KEY"] = _secret

# Harden the session cookie.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("BBI_ENV") == "production",
)

# Per-transaction ceiling for this demo: ₹10 crore (SECURITY H2).
# ₹10 crore = 100,000,000 rupees = 10,000,000,000 paise.
MAX_TXN_PAISE = 10_000_000_000


# --------------------------------------------------------------------------- #
# CSRF protection (lightweight, standard-library only) — SECURITY H1
# --------------------------------------------------------------------------- #
def csrf_token():
    """Return the per-session CSRF token, minting one on first use."""
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_hex(32)
        session["_csrf_token"] = token
    return token


def csrf_field():
    """Hidden <input> to drop inside every POST <form>."""
    return Markup(
        f'<input type="hidden" name="_csrf_token" value="{csrf_token()}">'
    )


@app.before_request
def csrf_protect():
    # Skip during automated tests (test client can't easily carry a token).
    if current_app.testing:
        return
    if request.method == "POST":
        sent = request.form.get("_csrf_token", "")
        expected = session.get("_csrf_token", "")
        if not (expected and hmac.compare_digest(str(sent), str(expected))):
            abort(400, description="Invalid or missing CSRF token.")


# --------------------------------------------------------------------------- #
# Database helpers
# --------------------------------------------------------------------------- #
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_FILE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_FILE)
    db.execute("PRAGMA foreign_keys = ON")   # enforce FK constraints (POLISH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name     TEXT    NOT NULL,
            email         TEXT    NOT NULL UNIQUE,
            phone         TEXT    NOT NULL,
            password_hash TEXT    NOT NULL,
            created_at    TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS accounts (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL,
            account_number TEXT    NOT NULL UNIQUE,
            account_type   TEXT    NOT NULL,
            ifsc           TEXT    NOT NULL,
            balance_paise  INTEGER NOT NULL DEFAULT 0,
            status         TEXT    NOT NULL DEFAULT 'ACTIVE',
            created_at     TEXT    NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id     INTEGER NOT NULL,
            txn_type       TEXT    NOT NULL,          -- CREDIT / DEBIT
            amount_paise   INTEGER NOT NULL,
            balance_paise  INTEGER NOT NULL,          -- running balance after txn
            category       TEXT    NOT NULL,          -- DEPOSIT / WITHDRAWAL / TRANSFER / FD / RD / LOAN
            description    TEXT    NOT NULL,
            counterparty   TEXT,
            ref_no         TEXT    NOT NULL,
            created_at     TEXT    NOT NULL,
            FOREIGN KEY (account_id) REFERENCES accounts (id)
        );

        -- Account-holder KYC / personal information (one row per user).
        CREATE TABLE IF NOT EXISTS customer_profiles (
            user_id             INTEGER PRIMARY KEY,
            dob                 TEXT,
            gender              TEXT,
            address             TEXT,
            city                TEXT,
            state               TEXT,
            pincode             TEXT,
            pan                 TEXT,
            aadhaar_last4       TEXT,
            occupation          TEXT,
            annual_income_paise INTEGER,
            nominee_name        TEXT,
            nominee_relation    TEXT,
            kyc_status          TEXT NOT NULL DEFAULT 'PENDING',   -- PENDING / VERIFIED
            updated_at          TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        -- Catalogue of deposit / savings schemes (banking information).
        CREATE TABLE IF NOT EXISTS schemes (
            code              TEXT PRIMARY KEY,
            name              TEXT NOT NULL,
            category          TEXT NOT NULL,          -- FD / RD / SAVINGS / GOVT
            interest_rate     REAL NOT NULL,
            min_tenure_months INTEGER,
            max_tenure_months INTEGER,
            min_amount_paise  INTEGER,
            openable          INTEGER NOT NULL DEFAULT 0,  -- 1 = customer can open online
            description       TEXT,
            highlight         TEXT
        );

        -- Catalogue of loan products (banking information).
        CREATE TABLE IF NOT EXISTS loan_products (
            code               TEXT PRIMARY KEY,
            name               TEXT NOT NULL,
            interest_rate      REAL NOT NULL,
            min_amount_paise   INTEGER,
            max_amount_paise   INTEGER,
            max_tenure_months  INTEGER,
            processing_fee_pct REAL,
            description        TEXT
        );

        -- Customer term deposits (Fixed / Recurring).
        CREATE TABLE IF NOT EXISTS deposits (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id              INTEGER NOT NULL,
            deposit_type         TEXT NOT NULL,       -- FD / RD
            scheme_code          TEXT NOT NULL,
            scheme_name          TEXT NOT NULL,
            principal_paise      INTEGER NOT NULL,    -- FD: lump sum; RD: monthly installment
            interest_rate        REAL NOT NULL,
            tenure_months        INTEGER NOT NULL,
            maturity_paise       INTEGER NOT NULL,
            total_invested_paise INTEGER NOT NULL,
            interest_paise       INTEGER NOT NULL,
            installments_paid    INTEGER NOT NULL DEFAULT 0,  -- RD only
            start_date           TEXT NOT NULL,
            maturity_date        TEXT NOT NULL,
            status               TEXT NOT NULL DEFAULT 'ACTIVE',   -- ACTIVE / MATURED / CLOSED
            ref_no               TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        -- Customer loans.
        CREATE TABLE IF NOT EXISTS loans (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id              INTEGER NOT NULL,
            product_code         TEXT NOT NULL,
            product_name         TEXT NOT NULL,
            loan_account         TEXT NOT NULL UNIQUE,
            principal_paise      INTEGER NOT NULL,
            interest_rate        REAL NOT NULL,
            tenure_months        INTEGER NOT NULL,
            emi_paise            INTEGER NOT NULL,
            total_payable_paise  INTEGER NOT NULL,
            total_interest_paise INTEGER NOT NULL,
            outstanding_paise    INTEGER NOT NULL,
            emis_paid            INTEGER NOT NULL DEFAULT 0,
            status               TEXT NOT NULL,        -- PENDING / ACTIVE / REJECTED / CLOSED
            decision_reason      TEXT,
            purpose              TEXT,
            applied_at           TEXT NOT NULL,
            decided_at           TEXT,
            ref_no               TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        );

        -- Loan EMI repayment ledger.
        CREATE TABLE IF NOT EXISTS loan_payments (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            loan_id           INTEGER NOT NULL,
            emi_no            INTEGER NOT NULL,
            amount_paise      INTEGER NOT NULL,
            principal_paise   INTEGER NOT NULL,
            interest_paise    INTEGER NOT NULL,
            outstanding_paise INTEGER NOT NULL,
            paid_at           TEXT NOT NULL,
            ref_no            TEXT NOT NULL,
            FOREIGN KEY (loan_id) REFERENCES loans (id)
        );

        -- Performance indexes (see PERFORMANCE.md) --
        CREATE INDEX IF NOT EXISTS idx_txn_account_created  ON transactions(account_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_accounts_user        ON accounts(user_id);
        CREATE INDEX IF NOT EXISTS idx_accounts_number      ON accounts(account_number);
        CREATE INDEX IF NOT EXISTS idx_deposits_user_status ON deposits(user_id, status);
        CREATE INDEX IF NOT EXISTS idx_loans_user_status    ON loans(user_id, status);
        CREATE INDEX IF NOT EXISTS idx_loans_account        ON loans(loan_account);
        CREATE INDEX IF NOT EXISTS idx_loan_payments_loan   ON loan_payments(loan_id);
        """
    )
    db.commit()
    seed_reference_data(db)
    db.close()


# --------------------------------------------------------------------------- #
# Seed data — banking information: schemes & loan products
# --------------------------------------------------------------------------- #
SCHEMES_SEED = [
    # code, name, category, rate, min_m, max_m, min_amount_paise, openable, description, highlight
    ("FD-REG", "Bharath Fixed Deposit", "FD", 7.00, 6, 120, 100000, 1,
     "Lock in a lump sum and earn a guaranteed return with quarterly compounding.",
     "Most popular"),
    ("FD-SENIOR", "Senior Citizen Fixed Deposit", "FD", 7.50, 6, 120, 100000, 1,
     "An extra 0.50% p.a. for account holders aged 60 and above.",
     "+0.50% p.a."),
    ("FD-TAX", "Bharath Tax Saver FD (5 years)", "FD", 7.25, 60, 60, 100000, 1,
     "5-year lock-in fixed deposit eligible for tax deduction under Sec 80C.",
     "Tax benefit"),
    ("RD-REG", "Bharath Recurring Deposit", "RD", 6.50, 12, 60, 50000, 1,
     "Invest a fixed amount every month and build a corpus over time.",
     "Save monthly"),
    ("SAV-REG", "Bharath Savings Account", "SAVINGS", 3.50, None, None, 0, 0,
     "Everyday savings account with instant transfers and no minimum balance.",
     "Zero balance"),
    ("PPF", "Bharath Public Provident Fund", "GOVT", 7.10, 180, 180, 50000, 0,
     "15-year government-backed long-term savings with tax-free interest.",
     "Govt backed"),
    ("SCSS", "Senior Citizen Savings Scheme", "GOVT", 8.20, 60, 60, 100000, 0,
     "Government scheme offering high assured returns for senior citizens.",
     "8.20% p.a."),
]

LOAN_PRODUCTS_SEED = [
    # code, name, rate, min_amount_paise, max_amount_paise, max_tenure_months, fee_pct, description
    ("LN-PERSONAL", "Personal Loan", 11.50, 5000000, 200000000, 60, 1.50,
     "Instant funds for any personal need — no collateral required."),
    ("LN-HOME", "Home Loan", 8.50, 50000000, 10000000000, 360, 0.50,
     "Own your dream home with long tenures and low interest rates."),
    ("LN-VEHICLE", "Vehicle Loan", 9.50, 10000000, 5000000000, 84, 1.00,
     "Finance a new or used car / two-wheeler at attractive rates."),
    ("LN-EDU", "Education Loan", 9.00, 5000000, 4000000000, 120, 0.50,
     "Fund higher studies in India or abroad with a flexible repayment plan."),
    ("LN-GOLD", "Gold Loan", 8.00, 1000000, 2500000000, 36, 0.75,
     "Quick loan against your gold with same-day disbursal."),
]


def seed_reference_data(db):
    if not db.execute("SELECT 1 FROM schemes LIMIT 1").fetchone():
        db.executemany(
            "INSERT INTO schemes (code, name, category, interest_rate, min_tenure_months,"
            " max_tenure_months, min_amount_paise, openable, description, highlight)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", SCHEMES_SEED)
    if not db.execute("SELECT 1 FROM loan_products LIMIT 1").fetchone():
        db.executemany(
            "INSERT INTO loan_products (code, name, interest_rate, min_amount_paise,"
            " max_amount_paise, max_tenure_months, processing_fee_pct, description)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)", LOAN_PRODUCTS_SEED)
    db.commit()


# --------------------------------------------------------------------------- #
# Money + formatting helpers
# --------------------------------------------------------------------------- #
def rupees_to_paise(value):
    """Accepts a string/number of rupees and returns integer paise. Raises ValueError."""
    rupees = float(value)                       # non-numeric -> ValueError (handled by callers)
    if not math.isfinite(rupees):               # reject nan / inf / -inf (SECURITY H2)
        raise ValueError("Amount must be a finite number.")
    amount = round(rupees * 100)
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    if amount > MAX_TXN_PAISE:
        raise ValueError("Amount exceeds the per-transaction limit.")
    return int(amount)


def fmt_inr(paise):
    """Format integer paise as Indian-grouped rupees, e.g. 1234567 -> '₹12,345.67'."""
    rupees = paise / 100
    whole = int(paise) // 100
    frac = int(paise) % 100
    s = str(whole)
    if len(s) > 3:
        last3 = s[-3:]
        rest = s[:-3]
        # Indian grouping: group the remaining digits in pairs
        parts = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        grouped = ",".join(parts) + "," + last3
    else:
        grouped = s
    return f"₹{grouped}.{frac:02d}"


app.jinja_env.filters["inr"] = fmt_inr


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def gen_account_number(db):
    """Generate a unique 12-digit account number prefixed by branch code."""
    while True:
        number = "1729" + "".join(str(random.randint(0, 9)) for _ in range(8))
        row = db.execute(
            "SELECT 1 FROM accounts WHERE account_number = ?", (number,)
        ).fetchone()
        if not row:
            return number


def gen_ref_no():
    return "BBI" + datetime.now().strftime("%y%m%d") + "".join(
        str(random.randint(0, 9)) for _ in range(6)
    )


# --------------------------------------------------------------------------- #
# Auth helpers
# --------------------------------------------------------------------------- #
def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_globals():
    return {
        "BANK_NAME": BANK_NAME,
        "BANK_SHORT": BANK_SHORT,
        "IFSC_CODE": IFSC_CODE,
        "BRANCH_NAME": BRANCH_NAME,
        "current_user": get_current_user(),
        "year": datetime.now().year,
        "csrf_field": csrf_field,
    }


def get_current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


def get_primary_account(user_id):
    return get_db().execute(
        "SELECT * FROM accounts WHERE user_id = ? ORDER BY id LIMIT 1", (user_id,)
    ).fetchone()


def get_profile(user_id):
    return get_db().execute(
        "SELECT * FROM customer_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()


def deposits_for(user_id, status=None):
    q = "SELECT * FROM deposits WHERE user_id = ?"
    p = [user_id]
    if status:
        q += " AND status = ?"
        p.append(status)
    q += " ORDER BY id DESC"
    return get_db().execute(q, p).fetchall()


def loans_for(user_id, status=None):
    q = "SELECT * FROM loans WHERE user_id = ?"
    p = [user_id]
    if status:
        q += " AND status = ?"
        p.append(status)
    q += " ORDER BY id DESC"
    return get_db().execute(q, p).fetchall()


def portfolio_summary(user_id):
    """Real-time roll-up of the customer's holdings across the backend tables."""
    db = get_db()
    deposits = db.execute(
        "SELECT COUNT(*) c,"
        " COALESCE(SUM(CASE WHEN deposit_type = 'RD'"
        "   THEN installments_paid * principal_paise ELSE total_invested_paise END), 0) invested,"
        " COALESCE(SUM(maturity_paise), 0) maturity FROM deposits"
        " WHERE user_id = ? AND status = 'ACTIVE'", (user_id,)).fetchone()
    loans = db.execute(
        "SELECT COUNT(*) c, COALESCE(SUM(outstanding_paise), 0) outstanding FROM loans"
        " WHERE user_id = ? AND status = 'ACTIVE'", (user_id,)).fetchone()
    return {
        "deposit_count": deposits["c"],
        "deposit_invested": deposits["invested"],
        "deposit_maturity": deposits["maturity"],
        "loan_count": loans["c"],
        "loan_outstanding": loans["outstanding"],
    }


def gen_loan_account(db):
    while True:
        number = "BBILN" + "".join(str(random.randint(0, 9)) for _ in range(8))
        if not db.execute("SELECT 1 FROM loans WHERE loan_account = ?", (number,)).fetchone():
            return number


# --------------------------------------------------------------------------- #
# Public pages
# --------------------------------------------------------------------------- #
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        account_type = request.form.get("account_type", "Savings")
        opening = request.form.get("opening_balance", "0").strip() or "0"

        error = None
        if not (full_name and email and phone and password):
            error = "All fields are required."
        elif password != confirm:
            error = "Passwords do not match."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."

        opening_paise = 0
        if error is None:
            try:
                opening_val = float(opening)
                if not math.isfinite(opening_val) or opening_val < 0:
                    raise ValueError
                opening_paise = round(opening_val * 100)
                if opening_paise > MAX_TXN_PAISE:
                    raise ValueError
            except ValueError:
                error = "Opening balance must be a valid non-negative amount."

        if error is None:
            db = get_db()
            existing = db.execute(
                "SELECT 1 FROM users WHERE email = ?", (email,)
            ).fetchone()
            if existing:
                error = "An account with that email already exists."
            else:
                created = now_str()
                cur = db.execute(
                    "INSERT INTO users (full_name, email, phone, password_hash, created_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (full_name, email, phone, generate_password_hash(password), created),
                )
                user_id = cur.lastrowid
                acc_number = gen_account_number(db)
                acc_cur = db.execute(
                    "INSERT INTO accounts (user_id, account_number, account_type, ifsc,"
                    " balance_paise, status, created_at) VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?)",
                    (user_id, acc_number, account_type, IFSC_CODE, opening_paise, created),
                )
                if opening_paise > 0:
                    db.execute(
                        "INSERT INTO transactions (account_id, txn_type, amount_paise,"
                        " balance_paise, category, description, counterparty, ref_no, created_at)"
                        " VALUES (?, 'CREDIT', ?, ?, 'DEPOSIT', ?, ?, ?, ?)",
                        (acc_cur.lastrowid, opening_paise, opening_paise,
                         "Opening deposit", "Self", gen_ref_no(), created),
                    )
                db.commit()
                session.clear()                 # rotate session id — prevent fixation (SECURITY M1)
                session["user_id"] = user_id
                flash(f"Welcome to {BANK_NAME}! Your account number is {acc_number}.", "success")
                return redirect(url_for("dashboard"))

        flash(error, "danger")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            flash(f"Welcome back, {user['full_name'].split()[0]}!", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out securely.", "info")
    return redirect(url_for("index"))


# --------------------------------------------------------------------------- #
# Authenticated banking pages
# --------------------------------------------------------------------------- #
@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    uid = session["user_id"]
    account = get_primary_account(uid)
    txns = db.execute(
        "SELECT * FROM transactions WHERE account_id = ? ORDER BY id DESC LIMIT 5",
        (account["id"],),
    ).fetchall()
    return render_template(
        "dashboard.html", account=account, txns=txns,
        summary=portfolio_summary(uid), profile=get_profile(uid),
    )


@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    account = get_primary_account(session["user_id"])
    if request.method == "POST":
        try:
            amount = rupees_to_paise(request.form.get("amount", ""))
        except ValueError as e:
            flash(str(e), "danger")
            return redirect(url_for("deposit"))
        desc = request.form.get("description", "").strip() or "Cash deposit"
        _post_transaction(account["id"], "CREDIT", amount, "DEPOSIT", desc, "Self")
        flash(f"{fmt_inr(amount)} deposited successfully.", "success")
        return redirect(url_for("dashboard"))
    return render_template("deposit.html", account=account)


@app.route("/withdraw", methods=["GET", "POST"])
@login_required
def withdraw():
    account = get_primary_account(session["user_id"])
    if request.method == "POST":
        try:
            amount = rupees_to_paise(request.form.get("amount", ""))
        except ValueError as e:
            flash(str(e), "danger")
            return redirect(url_for("withdraw"))
        # Re-read balance to avoid stale reads
        current = get_db().execute(
            "SELECT balance_paise FROM accounts WHERE id = ?", (account["id"],)
        ).fetchone()["balance_paise"]
        if amount > current:
            flash("Insufficient balance for this withdrawal.", "danger")
            return redirect(url_for("withdraw"))
        desc = request.form.get("description", "").strip() or "Cash withdrawal"
        _post_transaction(account["id"], "DEBIT", amount, "WITHDRAWAL", desc, "Self")
        flash(f"{fmt_inr(amount)} withdrawn successfully.", "success")
        return redirect(url_for("dashboard"))
    return render_template("withdraw.html", account=account)


@app.route("/transfer", methods=["GET", "POST"])
@login_required
def transfer():
    account = get_primary_account(session["user_id"])
    if request.method == "POST":
        to_number = request.form.get("to_account", "").strip()
        try:
            amount = rupees_to_paise(request.form.get("amount", ""))
        except ValueError as e:
            flash(str(e), "danger")
            return redirect(url_for("transfer"))
        desc = request.form.get("description", "").strip() or "Fund transfer"

        db = get_db()
        payee = db.execute(
            "SELECT a.*, u.full_name FROM accounts a JOIN users u ON u.id = a.user_id"
            " WHERE a.account_number = ?", (to_number,),
        ).fetchone()

        if not payee:
            flash("Payee account number not found in Bharath Bank of India.", "danger")
            return redirect(url_for("transfer"))
        if payee["id"] == account["id"]:
            flash("You cannot transfer money to your own account.", "danger")
            return redirect(url_for("transfer"))

        sender_balance = db.execute(
            "SELECT balance_paise FROM accounts WHERE id = ?", (account["id"],)
        ).fetchone()["balance_paise"]
        if amount > sender_balance:
            flash("Insufficient balance for this transfer.", "danger")
            return redirect(url_for("transfer"))

        ref = gen_ref_no()
        payer = get_current_user()
        # Atomic double-entry: debit sender, credit payee, share one ref number
        _post_transaction(account["id"], "DEBIT", amount, "TRANSFER",
                          f"To {payee['full_name']} — {desc}", to_number, ref=ref, commit=False)
        _post_transaction(payee["id"], "CREDIT", amount, "TRANSFER",
                          f"From {payer['full_name']} — {desc}",
                          account["account_number"], ref=ref, commit=False)
        db.commit()
        flash(f"{fmt_inr(amount)} transferred to {payee['full_name']} (Ref {ref}).", "success")
        return redirect(url_for("dashboard"))
    return render_template("transfer.html", account=account)


@app.route("/transactions")
@login_required
def transactions():
    account = get_primary_account(session["user_id"])
    txn_filter = request.args.get("type", "ALL")
    query = "SELECT * FROM transactions WHERE account_id = ?"
    params = [account["id"]]
    if txn_filter in ("CREDIT", "DEBIT"):
        query += " AND txn_type = ?"
        params.append(txn_filter)
    query += " ORDER BY id DESC"
    txns = get_db().execute(query, params).fetchall()
    return render_template("transactions.html", account=account, txns=txns,
                           txn_filter=txn_filter)


@app.route("/profile")
@login_required
def profile():
    uid = session["user_id"]
    account = get_primary_account(uid)
    return render_template("profile.html", account=account, profile=get_profile(uid))


# --------------------------------------------------------------------------- #
# Account-holder information (KYC)
# --------------------------------------------------------------------------- #
@app.route("/kyc", methods=["GET", "POST"])
@login_required
def kyc():
    uid = session["user_id"]
    profile = get_profile(uid)
    if request.method == "POST":
        f = request.form
        income_raw = f.get("annual_income", "").strip()
        try:
            if income_raw:
                income_val = float(income_raw)
                if not math.isfinite(income_val) or income_val < 0:
                    raise ValueError
                income_paise = round(income_val * 100)
            else:
                income_paise = None
        except ValueError:
            flash("Annual income must be a valid amount.", "danger")
            return redirect(url_for("kyc"))

        # --- KYC identity format validation (SECURITY M3) ---
        pan = f.get("pan", "").strip().upper()
        aadhaar = f.get("aadhaar", "").strip()
        if pan and not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", pan):
            flash("PAN must be in the format ABCDE1234F.", "danger")
            return redirect(url_for("kyc"))
        if aadhaar and not re.fullmatch(r"[0-9]{12}", aadhaar):
            flash("Aadhaar must be exactly 12 digits.", "danger")
            return redirect(url_for("kyc"))

        fields = dict(
            dob=f.get("dob", "").strip(),
            gender=f.get("gender", "").strip(),
            address=f.get("address", "").strip(),
            city=f.get("city", "").strip(),
            state=f.get("state", "").strip(),
            pincode=f.get("pincode", "").strip(),
            pan=pan,
            aadhaar_last4=aadhaar[-4:],
            occupation=f.get("occupation", "").strip(),
            annual_income_paise=income_paise,
            nominee_name=f.get("nominee_name", "").strip(),
            nominee_relation=f.get("nominee_relation", "").strip(),
        )
        # KYC is considered VERIFIED once the core identity fields are present.
        verified = all([fields["dob"], fields["address"], fields["pan"],
                        fields["aadhaar_last4"], fields["annual_income_paise"]])
        fields["kyc_status"] = "VERIFIED" if verified else "PENDING"
        fields["updated_at"] = now_str()

        db = get_db()
        cols = ", ".join(fields.keys())
        placeholders = ", ".join(["?"] * len(fields))
        updates = ", ".join(f"{k} = excluded.{k}" for k in fields)
        db.execute(
            f"INSERT INTO customer_profiles (user_id, {cols}) VALUES (?, {placeholders})"
            f" ON CONFLICT(user_id) DO UPDATE SET {updates}",
            [uid] + list(fields.values()),
        )
        db.commit()
        flash("Your details have been saved." +
              (" KYC is now verified." if verified else
               " Complete the identity fields to finish KYC."),
              "success" if verified else "info")
        return redirect(url_for("profile"))
    return render_template("kyc.html", profile=profile)


# --------------------------------------------------------------------------- #
# Banking information — schemes & loan products (public)
# --------------------------------------------------------------------------- #
@app.route("/products")
def products():
    db = get_db()
    schemes = db.execute(
        "SELECT * FROM schemes ORDER BY CASE category WHEN 'FD' THEN 1 WHEN 'RD' THEN 2"
        " WHEN 'SAVINGS' THEN 3 ELSE 4 END, interest_rate DESC").fetchall()
    loan_products = db.execute(
        "SELECT * FROM loan_products ORDER BY interest_rate").fetchall()
    return render_template("products.html", schemes=schemes, loan_products=loan_products)


# --------------------------------------------------------------------------- #
# Financial schemes — Fixed & Recurring Deposits
# --------------------------------------------------------------------------- #
@app.route("/deposits")
@login_required
def deposits_page():
    uid = session["user_id"]
    return render_template(
        "deposits.html", account=get_primary_account(uid),
        deposits=deposits_for(uid), summary=portfolio_summary(uid))


@app.route("/deposits/open", methods=["GET", "POST"])
@login_required
def open_deposit():
    uid = session["user_id"]
    account = get_primary_account(uid)
    db = get_db()
    schemes = db.execute(
        "SELECT * FROM schemes WHERE openable = 1 ORDER BY category DESC, code").fetchall()

    if request.method == "POST":
        scheme = db.execute(
            "SELECT * FROM schemes WHERE code = ? AND openable = 1",
            (request.form.get("scheme_code", ""),)).fetchone()
        if not scheme:
            flash("Please choose a valid scheme.", "danger")
            return redirect(url_for("open_deposit"))
        try:
            amount = rupees_to_paise(request.form.get("amount", ""))
            tenure = int(request.form.get("tenure_months", ""))
            if tenure <= 0:
                raise ValueError
        except ValueError:
            flash("Enter a valid amount and a whole number of months.", "danger")
            return redirect(url_for("open_deposit"))

        if scheme["min_tenure_months"] and tenure < scheme["min_tenure_months"] or \
           scheme["max_tenure_months"] and tenure > scheme["max_tenure_months"]:
            flash(f"Tenure for {scheme['name']} must be {scheme['min_tenure_months']}–"
                  f"{scheme['max_tenure_months']} months.", "danger")
            return redirect(url_for("open_deposit"))
        if scheme["min_amount_paise"] and amount < scheme["min_amount_paise"]:
            flash(f"Minimum for {scheme['name']} is {fmt_inr(scheme['min_amount_paise'])}"
                  f"{' per month' if scheme['category'] == 'RD' else ''}.", "danger")
            return redirect(url_for("open_deposit"))

        balance = db.execute("SELECT balance_paise FROM accounts WHERE id = ?",
                             (account["id"],)).fetchone()["balance_paise"]
        if amount > balance:
            flash("Insufficient balance in your savings account.", "danger")
            return redirect(url_for("open_deposit"))

        dep_type = scheme["category"]           # FD or RD
        rate = scheme["interest_rate"]
        if dep_type == "FD":
            maturity = finance.fd_maturity_paise(amount, rate, tenure)
            total_invested = amount
            installments_paid = 0
        else:                                    # RD — debit first installment now
            maturity = finance.rd_maturity_paise(amount, rate, tenure)
            total_invested = amount * tenure
            installments_paid = 1
        interest = maturity - total_invested
        start = date.today()
        maturity_date = finance.add_months(start, tenure).isoformat()
        ref = gen_ref_no()

        _post_transaction(account["id"], "DEBIT", amount, dep_type,
                          f"{scheme['name']} ({dep_type}) opened", "Deposit",
                          ref=ref, commit=False)
        db.execute(
            "INSERT INTO deposits (user_id, deposit_type, scheme_code, scheme_name,"
            " principal_paise, interest_rate, tenure_months, maturity_paise,"
            " total_invested_paise, interest_paise, installments_paid, start_date,"
            " maturity_date, status, ref_no)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?)",
            (uid, dep_type, scheme["code"], scheme["name"], amount, rate, tenure,
             maturity, total_invested, interest, installments_paid,
             start.isoformat(), maturity_date, ref))
        db.commit()
        flash(f"{scheme['name']} opened. Projected maturity {fmt_inr(maturity)} "
              f"on {maturity_date}.", "success")
        return redirect(url_for("deposits_page"))

    return render_template("open_deposit.html", account=account, schemes=schemes)


@app.route("/deposits/<int:dep_id>/pay", methods=["POST"])
@login_required
def pay_rd(dep_id):
    uid = session["user_id"]
    db = get_db()
    dep = db.execute("SELECT * FROM deposits WHERE id = ? AND user_id = ?",
                     (dep_id, uid)).fetchone()
    if not dep or dep["deposit_type"] != "RD" or dep["status"] != "ACTIVE":
        flash("Recurring deposit not found.", "danger")
        return redirect(url_for("deposits_page"))
    if dep["installments_paid"] >= dep["tenure_months"]:
        flash("All installments for this RD have already been paid.", "info")
        return redirect(url_for("deposits_page"))
    account = get_primary_account(uid)
    balance = db.execute("SELECT balance_paise FROM accounts WHERE id = ?",
                         (account["id"],)).fetchone()["balance_paise"]
    inst = dep["principal_paise"]
    if inst > balance:
        flash("Insufficient balance for this installment.", "danger")
        return redirect(url_for("deposits_page"))
    ref = gen_ref_no()
    _post_transaction(account["id"], "DEBIT", inst, "RD",
                      f"{dep['scheme_name']} installment", "Deposit", ref=ref, commit=False)
    paid = dep["installments_paid"] + 1
    db.execute("UPDATE deposits SET installments_paid = ? WHERE id = ?", (paid, dep_id))
    db.commit()
    flash(f"Installment {paid}/{dep['tenure_months']} of {fmt_inr(inst)} paid.", "success")
    return redirect(url_for("deposits_page"))


@app.route("/deposits/<int:dep_id>/close", methods=["POST"])
@login_required
def close_deposit(dep_id):
    uid = session["user_id"]
    db = get_db()
    dep = db.execute("SELECT * FROM deposits WHERE id = ? AND user_id = ?",
                     (dep_id, uid)).fetchone()
    if not dep or dep["status"] != "ACTIVE":
        flash("Deposit not found or already closed.", "danger")
        return redirect(url_for("deposits_page"))
    account = get_primary_account(uid)
    matured = date.today().isoformat() >= dep["maturity_date"]
    if dep["deposit_type"] == "FD":
        deposited = dep["principal_paise"]
    else:
        deposited = dep["installments_paid"] * dep["principal_paise"]

    if matured:
        credit, note, new_status = dep["maturity_paise"], "matured", "MATURED"
    else:
        credit, note, new_status = deposited, "closed early (principal only, no interest)", "CLOSED"

    ref = gen_ref_no()
    _post_transaction(account["id"], "CREDIT", credit, dep["deposit_type"],
                      f"{dep['scheme_name']} {note}", "Deposit", ref=ref, commit=False)
    db.execute("UPDATE deposits SET status = ? WHERE id = ?", (new_status, dep_id))
    db.commit()
    flash(f"{fmt_inr(credit)} credited to your savings account ({note}).", "success")
    return redirect(url_for("deposits_page"))


# --------------------------------------------------------------------------- #
# Loans
# --------------------------------------------------------------------------- #
@app.route("/loans")
@login_required
def loans_page():
    uid = session["user_id"]
    db = get_db()
    return render_template(
        "loans.html", account=get_primary_account(uid), loans=loans_for(uid),
        products=db.execute("SELECT * FROM loan_products ORDER BY interest_rate").fetchall(),
        profile=get_profile(uid))


@app.route("/loans/apply", methods=["GET", "POST"])
@login_required
def apply_loan():
    uid = session["user_id"]
    db = get_db()
    account = get_primary_account(uid)
    profile = get_profile(uid)
    products = db.execute("SELECT * FROM loan_products ORDER BY interest_rate").fetchall()

    if request.method == "POST":
        product = db.execute("SELECT * FROM loan_products WHERE code = ?",
                             (request.form.get("product_code", ""),)).fetchone()
        if not product:
            flash("Please choose a valid loan product.", "danger")
            return redirect(url_for("apply_loan"))
        try:
            amount = rupees_to_paise(request.form.get("amount", ""))
            tenure = int(request.form.get("tenure_months", ""))
            if tenure <= 0:
                raise ValueError
        except ValueError:
            flash("Enter a valid amount and a whole number of months.", "danger")
            return redirect(url_for("apply_loan"))
        purpose = request.form.get("purpose", "").strip()

        if not profile or not profile["annual_income_paise"]:
            flash("Please complete your KYC (including annual income) before applying "
                  "for a loan.", "warning")
            return redirect(url_for("kyc"))

        rate = product["interest_rate"]
        # Real-time eligibility assessment
        reasons = []
        if amount < product["min_amount_paise"] or amount > product["max_amount_paise"]:
            reasons.append(f"Amount must be between {fmt_inr(product['min_amount_paise'])} "
                           f"and {fmt_inr(product['max_amount_paise'])}.")
        if tenure < 6 or tenure > product["max_tenure_months"]:
            reasons.append(f"Tenure must be between 6 and {product['max_tenure_months']} months.")

        emi = total_payable = total_interest = 0
        if not reasons:
            emi, total_payable, total_interest = finance.loan_totals(amount, rate, tenure)
            monthly_income = profile["annual_income_paise"] / 12
            if emi > 0.55 * monthly_income:                 # FOIR limit
                reasons.append("The EMI would exceed 55% of your monthly income (FOIR limit). "
                               "Try a smaller amount or a longer tenure.")

        approved = not reasons
        loan_account = gen_loan_account(db)
        ref = gen_ref_no()
        now = now_str()

        if approved:
            status, reason, outstanding = "ACTIVE", \
                "Approved instantly based on income and eligibility.", amount
            _post_transaction(account["id"], "CREDIT", amount, "LOAN",
                              f"{product['name']} disbursed ({loan_account})", "Loan",
                              ref=ref, commit=False)
            fee = round(amount * product["processing_fee_pct"] / 100)
            if fee > 0:
                _post_transaction(account["id"], "DEBIT", fee, "LOAN",
                                  f"{product['name']} processing fee ({loan_account})",
                                  "Loan", ref=gen_ref_no(), commit=False)
        else:
            status, reason, outstanding = "REJECTED", " ".join(reasons), 0
            if emi == 0:
                emi, total_payable, total_interest = finance.loan_totals(
                    max(amount, 1), rate, max(tenure, 1))

        db.execute(
            "INSERT INTO loans (user_id, product_code, product_name, loan_account,"
            " principal_paise, interest_rate, tenure_months, emi_paise, total_payable_paise,"
            " total_interest_paise, outstanding_paise, emis_paid, status, decision_reason,"
            " purpose, applied_at, decided_at, ref_no)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)",
            (uid, product["code"], product["name"], loan_account, amount, rate, tenure,
             emi, total_payable, total_interest, outstanding, status, reason, purpose,
             now, now, ref))
        db.commit()

        if approved:
            flash(f"Congratulations! Your {product['name']} of {fmt_inr(amount)} is approved "
                  f"and disbursed to your savings account. EMI {fmt_inr(emi)}/month.", "success")
            loan = db.execute("SELECT id FROM loans WHERE loan_account = ?",
                              (loan_account,)).fetchone()
            return redirect(url_for("loan_detail", loan_id=loan["id"]))
        flash(f"Your {product['name']} application could not be approved. {reason}", "danger")
        return redirect(url_for("loans_page"))

    return render_template("apply_loan.html", account=account, products=products,
                           profile=profile)


@app.route("/loans/<int:loan_id>")
@login_required
def loan_detail(loan_id):
    uid = session["user_id"]
    db = get_db()
    loan = db.execute("SELECT * FROM loans WHERE id = ? AND user_id = ?",
                      (loan_id, uid)).fetchone()
    if not loan:
        abort(404)
    schedule = payments = []
    if loan["status"] in ("ACTIVE", "CLOSED"):
        schedule = finance.amortization_schedule(
            loan["principal_paise"], loan["interest_rate"], loan["tenure_months"],
            loan["emi_paise"])
        payments = db.execute(
            "SELECT * FROM loan_payments WHERE loan_id = ? ORDER BY emi_no", (loan_id,)).fetchall()
    return render_template("loan_detail.html", loan=loan, schedule=schedule,
                           payments=payments, account=get_primary_account(uid))


@app.route("/loans/<int:loan_id>/pay", methods=["POST"])
@login_required
def pay_emi(loan_id):
    uid = session["user_id"]
    db = get_db()
    loan = db.execute("SELECT * FROM loans WHERE id = ? AND user_id = ?",
                      (loan_id, uid)).fetchone()
    if not loan or loan["status"] != "ACTIVE":
        flash("Loan not found or not active.", "danger")
        return redirect(url_for("loans_page"))
    account = get_primary_account(uid)
    balance = db.execute("SELECT balance_paise FROM accounts WHERE id = ?",
                         (account["id"],)).fetchone()["balance_paise"]
    interest, principal, pay, new_out = finance.emi_split(
        loan["outstanding_paise"], loan["interest_rate"], loan["emi_paise"])
    if pay > balance:
        flash("Insufficient balance to pay this EMI.", "danger")
        return redirect(url_for("loan_detail", loan_id=loan_id))

    ref = gen_ref_no()
    _post_transaction(account["id"], "DEBIT", pay, "LOAN",
                      f"{loan['product_name']} EMI ({loan['loan_account']})", "Loan",
                      ref=ref, commit=False)
    emi_no = loan["emis_paid"] + 1
    db.execute(
        "INSERT INTO loan_payments (loan_id, emi_no, amount_paise, principal_paise,"
        " interest_paise, outstanding_paise, paid_at, ref_no)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (loan_id, emi_no, pay, principal, interest, new_out, now_str(), ref))
    new_status = "CLOSED" if new_out <= 0 else "ACTIVE"
    db.execute("UPDATE loans SET outstanding_paise = ?, emis_paid = ?, status = ? WHERE id = ?",
               (new_out, emi_no, new_status, loan_id))
    db.commit()
    if new_out <= 0:
        flash(f"Final EMI of {fmt_inr(pay)} paid. Loan {loan['loan_account']} "
              f"is now fully closed! 🎉", "success")
    else:
        flash(f"EMI {emi_no}/{loan['tenure_months']} of {fmt_inr(pay)} paid. "
              f"Outstanding {fmt_inr(new_out)}.", "success")
    return redirect(url_for("loan_detail", loan_id=loan_id))


# --------------------------------------------------------------------------- #
# Simple JSON API (for programmatic access / demonstration)
# --------------------------------------------------------------------------- #
@app.route("/api/balance")
@login_required
def api_balance():
    account = get_primary_account(session["user_id"])
    return jsonify({
        "account_number": account["account_number"],
        "ifsc": account["ifsc"],
        "balance": account["balance_paise"] / 100,
        "currency": "INR",
    })


# --------------------------------------------------------------------------- #
# Account statement export
# --------------------------------------------------------------------------- #
def _statement_context():
    """Shared helper: resolve the current account, date filters and rows."""
    account = get_primary_account(session["user_id"])
    start = request.args.get("start") or None
    end = request.args.get("end") or None
    rows = statement_rows(get_db(), account["id"], start=start, end=end)
    bank_meta = {
        "name": BANK_NAME,
        "ifsc": IFSC_CODE,
        "branch": BRANCH_NAME,
        "period": (f"{start or 'Beginning'} to {end or 'Present'}"),
    }
    return account, rows, bank_meta


@app.route("/statement.csv")
@login_required
def statement_csv():
    account, rows, bank_meta = _statement_context()
    csv_text = to_csv(rows, account, bank_meta)
    filename = f"statement_{account['account_number']}.csv"
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@app.route("/statement/print")
@login_required
def statement_print():
    account, rows, bank_meta = _statement_context()
    html_text = to_printable_html(rows, account, bank_meta)
    return Response(html_text, mimetype="text/html")


# --------------------------------------------------------------------------- #
# Core transaction engine
# --------------------------------------------------------------------------- #
def _post_transaction(account_id, txn_type, amount_paise, category, description,
                      counterparty, ref=None, commit=True):
    """Apply a single ledger entry and update the running account balance."""
    db = get_db()
    # Atomic balance update at the SQL level so the DB — not stale Python state —
    # enforces the balance floor, closing the double-submit / lost-update race
    # and overdraft window in one statement (SECURITY M2).
    if txn_type == "CREDIT":
        db.execute(
            "UPDATE accounts SET balance_paise = balance_paise + ? WHERE id = ?",
            (amount_paise, account_id),
        )
    else:
        cur = db.execute(
            "UPDATE accounts SET balance_paise = balance_paise - ?"
            " WHERE id = ? AND balance_paise >= ?",
            (amount_paise, account_id, amount_paise),
        )
        if cur.rowcount == 0:
            raise ValueError("Insufficient balance.")
    balance = db.execute(
        "SELECT balance_paise FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()["balance_paise"]

    db.execute(
        "INSERT INTO transactions (account_id, txn_type, amount_paise, balance_paise,"
        " category, description, counterparty, ref_no, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (account_id, txn_type, amount_paise, balance, category, description,
         counterparty, ref or gen_ref_no(), now_str()),
    )
    if commit:
        db.commit()
    return balance


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    init_db()
    # Register admin blueprint (late import to avoid circular dependency with admin.py)
    from admin import admin_bp
    app.register_blueprint(admin_bp)
    print(f"  {BANK_NAME}  —  internet banking server")
    print(f"  Database: {DB_FILE}")
    port = int(os.environ.get("PORT", 5055))
    print(f"  Open http://127.0.0.1:{port} in your browser")
    app.run(host="127.0.0.1", port=port,
            debug=os.environ.get("BBI_ENV") != "production")
