"""
Admin console for Bharath Bank of India — a self-contained Flask Blueprint.

This is a *demonstration* back-office panel. The main customer app has no admin
user system, so this console is protected by a single shared password kept in
the environment variable ``BBI_ADMIN_PASS`` (default ``admin123``). Signing in
simply sets ``session['is_admin'] = True``.

To wire it into the app, add ONE line near the bottom of ``app.py`` (see
ADMIN_README.md)::

    from admin import admin_bp
    app.register_blueprint(admin_bp)

The blueprint reuses the main app's database helpers, money formatter and the
``inr`` Jinja filter, so it stays perfectly consistent with the rest of the
site and touches the very same ``bank.db``.
"""

import os
import functools
from datetime import datetime

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    session, flash, abort,
)

# Reuse the exact helpers already defined by the main application.
from app import get_db, fmt_inr

# --------------------------------------------------------------------------- #
# Blueprint + configuration
# --------------------------------------------------------------------------- #
admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# Shared demo password. Override with:  set BBI_ADMIN_PASS=your-password
ADMIN_PASS = os.environ.get("BBI_ADMIN_PASS", "admin123")


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
def admin_required(view):
    """Gate a view behind the shared admin password (session['is_admin'])."""
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Please sign in to the admin console.", "warning")
            return redirect(url_for("admin.login"))
        return view(*args, **kwargs)
    return wrapped


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("is_admin"):
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        if request.form.get("password", "") == ADMIN_PASS:
            session["is_admin"] = True
            flash("Welcome to the admin console.", "success")
            return redirect(url_for("admin.dashboard"))
        flash("Incorrect admin password.", "danger")
    return render_template("admin/login.html")


@admin_bp.route("/logout")
def logout():
    session.pop("is_admin", None)
    flash("Signed out of the admin console.", "info")
    return redirect(url_for("admin.login"))


# --------------------------------------------------------------------------- #
# Dashboard — bank-wide totals
# --------------------------------------------------------------------------- #
@admin_bp.route("/")
@admin_required
def dashboard():
    db = get_db()

    customer_count = db.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]

    # "Total deposits" here = money held across all customer accounts.
    total_balance = db.execute(
        "SELECT COALESCE(SUM(balance_paise), 0) s FROM accounts"
    ).fetchone()["s"]

    # Active term deposits (FD / RD). Invested value mirrors the customer app's
    # roll-up: RD counts only installments actually paid.
    active_dep = db.execute(
        "SELECT COUNT(*) c,"
        " COALESCE(SUM(CASE WHEN deposit_type = 'RD'"
        "   THEN installments_paid * principal_paise ELSE total_invested_paise END), 0) invested,"
        " COALESCE(SUM(maturity_paise), 0) maturity"
        " FROM deposits WHERE status = 'ACTIVE'"
    ).fetchone()

    active_loans = db.execute(
        "SELECT COUNT(*) c, COALESCE(SUM(outstanding_paise), 0) outstanding"
        " FROM loans WHERE status = 'ACTIVE'"
    ).fetchone()

    pending_loans = db.execute(
        "SELECT COUNT(*) c FROM loans WHERE status = 'PENDING'"
    ).fetchone()["c"]

    return render_template(
        "admin/dashboard.html",
        customer_count=customer_count,
        total_balance=total_balance,
        active_dep=active_dep,
        active_loans=active_loans,
        pending_loans=pending_loans,
    )


# --------------------------------------------------------------------------- #
# Customers
# --------------------------------------------------------------------------- #
@admin_bp.route("/customers")
@admin_required
def customers():
    db = get_db()
    rows = db.execute(
        "SELECT u.id, u.full_name, u.email, u.phone, u.created_at,"
        " a.account_number, a.balance_paise,"
        " COALESCE(p.kyc_status, 'PENDING') AS kyc_status"
        " FROM users u"
        " LEFT JOIN accounts a"
        "   ON a.id = (SELECT id FROM accounts WHERE user_id = u.id ORDER BY id LIMIT 1)"
        " LEFT JOIN customer_profiles p ON p.user_id = u.id"
        " ORDER BY u.id"
    ).fetchall()
    return render_template("admin/customers.html", customers=rows)


@admin_bp.route("/customer/<int:uid>")
@admin_required
def customer(uid):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if not user:
        abort(404)

    profile = db.execute(
        "SELECT * FROM customer_profiles WHERE user_id = ?", (uid,)
    ).fetchone()
    accounts = db.execute(
        "SELECT * FROM accounts WHERE user_id = ? ORDER BY id", (uid,)
    ).fetchall()
    deposits = db.execute(
        "SELECT * FROM deposits WHERE user_id = ? ORDER BY id DESC", (uid,)
    ).fetchall()
    loans = db.execute(
        "SELECT * FROM loans WHERE user_id = ? ORDER BY id DESC", (uid,)
    ).fetchall()

    txns = []
    account_ids = [a["id"] for a in accounts]
    if account_ids:
        placeholders = ",".join("?" * len(account_ids))
        txns = db.execute(
            f"SELECT * FROM transactions WHERE account_id IN ({placeholders})"
            " ORDER BY id DESC LIMIT 15",
            account_ids,
        ).fetchall()

    return render_template(
        "admin/customer.html",
        user=user, profile=profile, accounts=accounts,
        deposits=deposits, loans=loans, txns=txns,
    )


# --------------------------------------------------------------------------- #
# Loans — review + manual approve / reject
# --------------------------------------------------------------------------- #
@admin_bp.route("/loans")
@admin_required
def loans():
    db = get_db()
    rows = db.execute(
        "SELECT l.*, u.full_name FROM loans l"
        " JOIN users u ON u.id = l.user_id"
        " ORDER BY CASE l.status WHEN 'PENDING' THEN 0 ELSE 1 END, l.id DESC"
    ).fetchall()
    pending_count = sum(1 for r in rows if r["status"] == "PENDING")
    return render_template("admin/loans.html", loans=rows, pending_count=pending_count)


@admin_bp.route("/loans/<int:loan_id>/decision", methods=["POST"])
@admin_required
def loan_decision(loan_id):
    """Manually approve or reject a PENDING loan (updates loans.status)."""
    db = get_db()
    loan = db.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
    if not loan:
        abort(404)
    if loan["status"] != "PENDING":
        flash("That loan has already been decided.", "warning")
        return redirect(url_for("admin.loans"))

    action = request.form.get("action", "")
    if action == "approve":
        db.execute(
            "UPDATE loans SET status = 'ACTIVE', outstanding_paise = principal_paise,"
            " decision_reason = ?, decided_at = ? WHERE id = ?",
            ("Approved manually by bank admin.", _now(), loan_id),
        )
        db.commit()
        flash(f"Loan {loan['loan_account']} ({fmt_inr(loan['principal_paise'])}) approved.",
              "success")
    elif action == "reject":
        db.execute(
            "UPDATE loans SET status = 'REJECTED', outstanding_paise = 0,"
            " decision_reason = ?, decided_at = ? WHERE id = ?",
            ("Rejected manually by bank admin.", _now(), loan_id),
        )
        db.commit()
        flash(f"Loan {loan['loan_account']} rejected.", "info")
    else:
        flash("Unknown action.", "danger")

    return redirect(url_for("admin.loans"))
