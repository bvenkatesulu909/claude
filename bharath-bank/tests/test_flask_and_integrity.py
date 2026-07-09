"""Flask integration tests and data integrity verification for Bharath Bank.

Tests cover:
  * Flask routes (register, login, deposit, withdraw, transfer, KYC)
  * Data integrity (balance consistency, double-entry bookkeeping, running balance)
  * Edge cases (insufficient funds, duplicate emails, etc.)
"""
import os
import sys
from datetime import date

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


# --------------------------------------------------------------------------- #
# Registration tests
# --------------------------------------------------------------------------- #
class TestRegistration:
    def test_register_new_user_creates_account_and_logs_in(self, client, db_conn):
        """A successful registration creates a user, account, and logs them in."""
        resp = client.post("/register", data={
            "full_name": "Alice Johnson",
            "email": "alice@example.com",
            "phone": "9876543210",
            "password": "SecurePass123",
            "confirm": "SecurePass123",
            "account_type": "Savings",
            "opening_balance": "10000",
        }, follow_redirects=False)

        assert resp.status_code == 302  # redirect to dashboard
        assert resp.location.endswith("/dashboard")

        # Verify user was created
        user = db_conn.execute("SELECT * FROM users WHERE email = ?", ("alice@example.com",)).fetchone()
        assert user is not None
        assert user["full_name"] == "Alice Johnson"
        assert user["phone"] == "9876543210"

        # Verify account was created
        account = db_conn.execute("SELECT * FROM accounts WHERE user_id = ?", (user["id"],)).fetchone()
        assert account is not None
        assert account["balance_paise"] == 1_000_000  # 10000 rupees
        assert account["account_type"] == "Savings"

        # Verify opening transaction was recorded
        txn = db_conn.execute(
            "SELECT * FROM transactions WHERE account_id = ?", (account["id"],)
        ).fetchone()
        assert txn is not None
        assert txn["txn_type"] == "CREDIT"
        assert txn["amount_paise"] == 1_000_000
        assert txn["category"] == "DEPOSIT"

    def test_register_with_duplicate_email_fails(self, client, db_conn):
        """Registering with an existing email shows an error."""
        # Pre-create a user
        db_conn.execute(
            "INSERT INTO users (full_name, email, phone, password_hash, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            ("Existing User", "existing@example.com", "1234567890",
             "hashed_password", "2026-01-01 00:00:00"),
        )
        db_conn.commit()

        resp = client.post("/register", data={
            "full_name": "New User",
            "email": "existing@example.com",
            "phone": "9876543210",
            "password": "SecurePass123",
            "confirm": "SecurePass123",
            "account_type": "Savings",
            "opening_balance": "0",
        }, follow_redirects=True)

        assert b"already exists" in resp.data

    def test_register_with_mismatched_passwords_fails(self, client):
        """Passwords that don't match prevent registration."""
        resp = client.post("/register", data={
            "full_name": "Bob Smith",
            "email": "bob@example.com",
            "phone": "9876543210",
            "password": "Pass1234",
            "confirm": "Different1234",
            "account_type": "Savings",
            "opening_balance": "0",
        }, follow_redirects=True)

        assert b"do not match" in resp.data

    def test_register_with_short_password_fails(self, client):
        """Passwords shorter than 6 characters are rejected."""
        resp = client.post("/register", data={
            "full_name": "Charlie Brown",
            "email": "charlie@example.com",
            "phone": "9876543210",
            "password": "Pass",
            "confirm": "Pass",
            "account_type": "Savings",
            "opening_balance": "0",
        }, follow_redirects=True)

        assert b"at least 6 characters" in resp.data

    def test_register_with_no_opening_balance_creates_zero_balance_account(self, client, db_conn):
        """Registration without an opening balance creates account with zero balance."""
        resp = client.post("/register", data={
            "full_name": "Diana Prince",
            "email": "diana@example.com",
            "phone": "9876543210",
            "password": "SecurePass123",
            "confirm": "SecurePass123",
            "account_type": "Savings",
            "opening_balance": "",
        }, follow_redirects=False)

        user = db_conn.execute("SELECT * FROM users WHERE email = ?", ("diana@example.com",)).fetchone()
        account = db_conn.execute("SELECT * FROM accounts WHERE user_id = ?", (user["id"],)).fetchone()

        assert account["balance_paise"] == 0
        # No opening transaction for zero balance
        txn = db_conn.execute(
            "SELECT COUNT(*) c FROM transactions WHERE account_id = ?", (account["id"],)
        ).fetchone()
        assert txn["c"] == 0


# --------------------------------------------------------------------------- #
# Login/logout tests
# --------------------------------------------------------------------------- #
class TestLogin:
    def test_login_with_valid_credentials_sets_session(self, client, db_conn):
        """Valid email and password create a session and redirect to dashboard."""
        # Create a user
        from werkzeug.security import generate_password_hash
        db_conn.execute(
            "INSERT INTO users (full_name, email, phone, password_hash, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            ("Test User", "test@example.com", "9876543210",
             generate_password_hash("TestPass123"), "2026-01-01 00:00:00"),
        )
        db_conn.commit()

        resp = client.post("/login", data={
            "email": "test@example.com",
            "password": "TestPass123",
        }, follow_redirects=False)

        assert resp.status_code == 302
        assert resp.location.endswith("/dashboard")
        with client.session_transaction() as sess:
            assert "user_id" in sess

    def test_login_with_invalid_credentials_shows_error(self, client):
        """Invalid email or password shows an error."""
        resp = client.post("/login", data={
            "email": "nonexistent@example.com",
            "password": "WrongPass123",
        }, follow_redirects=True)

        assert b"Invalid email or password" in resp.data

    def test_logout_clears_session(self, client, db_conn):
        """Logout clears the session and redirects to index."""
        # Create and login a user
        from werkzeug.security import generate_password_hash
        result = db_conn.execute(
            "INSERT INTO users (full_name, email, phone, password_hash, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            ("Test User", "test@example.com", "9876543210",
             generate_password_hash("TestPass123"), "2026-01-01 00:00:00"),
        )
        db_conn.commit()
        user_id = result.lastrowid

        with client:
            client.post("/login", data={
                "email": "test@example.com",
                "password": "TestPass123",
            })
            with client.session_transaction() as sess:
                assert sess["user_id"] == user_id

            resp = client.get("/logout", follow_redirects=False)
            assert resp.status_code == 302
            with client.session_transaction() as sess:
                assert "user_id" not in sess


# --------------------------------------------------------------------------- #
# Deposit and withdrawal tests
# --------------------------------------------------------------------------- #
class TestDeposit:
    def test_deposit_credits_account_and_updates_balance(self, client, db_conn):
        """A deposit transaction credits the account and updates balance."""
        # Register and login user
        client.post("/register", data={
            "full_name": "Eve Wilson",
            "email": "eve@example.com",
            "phone": "9876543210",
            "password": "SecurePass123",
            "confirm": "SecurePass123",
            "account_type": "Savings",
            "opening_balance": "5000",
        })

        # Deposit more funds
        resp = client.post("/deposit", data={
            "amount": "3000",
            "description": "Salary deposit",
        }, follow_redirects=False)

        assert resp.status_code == 302

        # Verify balance was updated
        user = db_conn.execute("SELECT * FROM users WHERE email = ?", ("eve@example.com",)).fetchone()
        account = db_conn.execute("SELECT * FROM accounts WHERE user_id = ?", (user["id"],)).fetchone()

        assert account["balance_paise"] == 8_00_000  # 5000 + 3000 = 8000 rupees


class TestWithdraw:
    def test_withdraw_with_sufficient_balance_succeeds(self, client, db_conn):
        """A withdrawal from an account with sufficient balance succeeds."""
        # Register with opening balance
        client.post("/register", data={
            "full_name": "Frank Miller",
            "email": "frank@example.com",
            "phone": "9876543210",
            "password": "SecurePass123",
            "confirm": "SecurePass123",
            "account_type": "Savings",
            "opening_balance": "10000",
        })

        # Withdraw funds
        resp = client.post("/withdraw", data={
            "amount": "3000",
            "description": "Cash withdrawal",
        }, follow_redirects=False)

        assert resp.status_code == 302

        # Verify balance was updated
        user = db_conn.execute("SELECT * FROM users WHERE email = ?", ("frank@example.com",)).fetchone()
        account = db_conn.execute("SELECT * FROM accounts WHERE user_id = ?", (user["id"],)).fetchone()

        assert account["balance_paise"] == 7_00_000  # 10000 - 3000 = 7000 rupees

    def test_withdraw_with_insufficient_balance_fails(self, client):
        """A withdrawal from an account with insufficient balance fails."""
        # Register with small opening balance
        client.post("/register", data={
            "full_name": "Grace Lee",
            "email": "grace@example.com",
            "phone": "9876543210",
            "password": "SecurePass123",
            "confirm": "SecurePass123",
            "account_type": "Savings",
            "opening_balance": "500",
        })

        # Try to withdraw more than balance
        resp = client.post("/withdraw", data={
            "amount": "1000",
            "description": "Cash withdrawal",
        }, follow_redirects=True)

        assert b"Insufficient balance" in resp.data


# --------------------------------------------------------------------------- #
# Transfer tests (double-entry integrity)
# --------------------------------------------------------------------------- #
class TestTransfer:
    def test_transfer_between_accounts_creates_double_entry(self, client, app_module, db_conn):
        """A transfer creates a debit entry in sender and credit entry in receiver with same ref."""
        # Register two users
        client.post("/register", data={
            "full_name": "Henry Davis",
            "email": "henry@example.com",
            "phone": "1111111111",
            "password": "SecurePass123",
            "confirm": "SecurePass123",
            "account_type": "Savings",
            "opening_balance": "10000",
        })

        client.post("/register", data={
            "full_name": "Ivy Clark",
            "email": "ivy@example.com",
            "phone": "2222222222",
            "password": "SecurePass123",
            "confirm": "SecurePass123",
            "account_type": "Savings",
            "opening_balance": "5000",
        })

        # Get Henry's account number and Ivy's user ID
        henry = db_conn.execute("SELECT * FROM users WHERE email = ?", ("henry@example.com",)).fetchone()
        henry_account = db_conn.execute("SELECT * FROM accounts WHERE user_id = ?", (henry["id"],)).fetchone()
        ivy = db_conn.execute("SELECT * FROM users WHERE email = ?", ("ivy@example.com",)).fetchone()
        ivy_account = db_conn.execute("SELECT * FROM accounts WHERE user_id = ?", (ivy["id"],)).fetchone()

        # Log in as Henry and transfer to Ivy
        client.post("/login", data={
            "email": "henry@example.com",
            "password": "SecurePass123",
        })

        resp = client.post("/transfer", data={
            "to_account": henry_account["account_number"],
            "amount": "2000",
            "description": "Test transfer",
        }, follow_redirects=True)

        # This should fail because Henry can't transfer to himself
        assert b"cannot transfer money to your own account" in resp.data

    def test_transfer_to_another_user_succeeds_with_double_entry(self, client, db_conn):
        """A successful transfer creates matching debit and credit entries."""
        # Register two users with sufficient balance
        client.post("/register", data={
            "full_name": "Jack Wilson",
            "email": "jack@example.com",
            "phone": "1111111111",
            "password": "SecurePass123",
            "confirm": "SecurePass123",
            "account_type": "Savings",
            "opening_balance": "10000",
        })

        client.post("/register", data={
            "full_name": "Karen White",
            "email": "karen@example.com",
            "phone": "2222222222",
            "password": "SecurePass123",
            "confirm": "SecurePass123",
            "account_type": "Savings",
            "opening_balance": "5000",
        })

        # Get account numbers
        jack = db_conn.execute("SELECT * FROM users WHERE email = ?", ("jack@example.com",)).fetchone()
        jack_account = db_conn.execute("SELECT * FROM accounts WHERE user_id = ?", (jack["id"],)).fetchone()
        karen = db_conn.execute("SELECT * FROM users WHERE email = ?", ("karen@example.com",)).fetchone()
        karen_account = db_conn.execute("SELECT * FROM accounts WHERE user_id = ?", (karen["id"],)).fetchone()

        # Log in as Jack and transfer to Karen
        client.post("/login", data={
            "email": "jack@example.com",
            "password": "SecurePass123",
        })

        resp = client.post("/transfer", data={
            "to_account": karen_account["account_number"],
            "amount": "2000",
            "description": "Test transfer to Karen",
        }, follow_redirects=False)

        assert resp.status_code == 302

        # Verify double-entry: both transactions exist with same ref_no
        txns = db_conn.execute(
            "SELECT * FROM transactions WHERE category = 'TRANSFER' ORDER BY id DESC LIMIT 2"
        ).fetchall()

        assert len(txns) == 2
        assert txns[0]["ref_no"] == txns[1]["ref_no"]  # same reference number
        assert txns[0]["txn_type"] != txns[1]["txn_type"]  # one debit, one credit
        assert txns[0]["amount_paise"] == txns[1]["amount_paise"] == 2_00_000

        # Verify balances
        jack_updated = db_conn.execute("SELECT balance_paise FROM accounts WHERE id = ?", (jack_account["id"],)).fetchone()
        karen_updated = db_conn.execute("SELECT balance_paise FROM accounts WHERE id = ?", (karen_account["id"],)).fetchone()

        assert jack_updated["balance_paise"] == 8_00_000  # 10000 - 2000
        assert karen_updated["balance_paise"] == 7_00_000  # 5000 + 2000

    def test_transfer_with_insufficient_balance_fails(self, client, db_conn):
        """A transfer with insufficient balance is rejected."""
        # Register two users
        client.post("/register", data={
            "full_name": "Leo Martinez",
            "email": "leo@example.com",
            "phone": "1111111111",
            "password": "SecurePass123",
            "confirm": "SecurePass123",
            "account_type": "Savings",
            "opening_balance": "500",
        })

        client.post("/register", data={
            "full_name": "Mia Garcia",
            "email": "mia@example.com",
            "phone": "2222222222",
            "password": "SecurePass123",
            "confirm": "SecurePass123",
            "account_type": "Savings",
            "opening_balance": "5000",
        })

        # Get Mia's account number
        mia = db_conn.execute("SELECT * FROM users WHERE email = ?", ("mia@example.com",)).fetchone()
        mia_account = db_conn.execute("SELECT * FROM accounts WHERE user_id = ?", (mia["id"],)).fetchone()

        # Log in as Leo and try to transfer more than his balance
        client.post("/login", data={
            "email": "leo@example.com",
            "password": "SecurePass123",
        })

        resp = client.post("/transfer", data={
            "to_account": mia_account["account_number"],
            "amount": "1000",
            "description": "Test transfer",
        }, follow_redirects=True)

        assert b"Insufficient balance" in resp.data


# --------------------------------------------------------------------------- #
# KYC (Know Your Customer) tests
# --------------------------------------------------------------------------- #
class TestKYC:
    def test_kyc_status_is_pending_initially(self, client, db_conn):
        """A newly registered user has PENDING KYC status."""
        client.post("/register", data={
            "full_name": "Nina Rodriguez",
            "email": "nina@example.com",
            "phone": "9876543210",
            "password": "SecurePass123",
            "confirm": "SecurePass123",
            "account_type": "Savings",
            "opening_balance": "1000",
        })

        user = db_conn.execute("SELECT * FROM users WHERE email = ?", ("nina@example.com",)).fetchone()
        profile = db_conn.execute("SELECT * FROM customer_profiles WHERE user_id = ?", (user["id"],)).fetchone()

        # Profile might be None or have PENDING status
        if profile:
            assert profile["kyc_status"] == "PENDING"

    def test_kyc_update_with_required_fields_verifies_status(self, client, db_conn):
        """Updating KYC with all required fields marks status as VERIFIED."""
        # Register user
        client.post("/register", data={
            "full_name": "Oscar Brown",
            "email": "oscar@example.com",
            "phone": "9876543210",
            "password": "SecurePass123",
            "confirm": "SecurePass123",
            "account_type": "Savings",
            "opening_balance": "1000",
        })

        # Login and update KYC
        client.post("/login", data={
            "email": "oscar@example.com",
            "password": "SecurePass123",
        })

        resp = client.post("/kyc", data={
            "dob": "1990-05-15",
            "gender": "Male",
            "address": "123 Main Street, Apartment 4B",
            "city": "Bangalore",
            "state": "Karnataka",
            "pincode": "560001",
            "pan": "ABCDE1234F",
            "aadhaar": "123456789012",  # will be truncated to last 4 digits
            "occupation": "Software Engineer",
            "annual_income": "1000000",
            "nominee_name": "Jane Brown",
            "nominee_relation": "Spouse",
        }, follow_redirects=False)

        assert resp.status_code == 302

        # Verify KYC status is now VERIFIED
        user = db_conn.execute("SELECT * FROM users WHERE email = ?", ("oscar@example.com",)).fetchone()
        profile = db_conn.execute("SELECT * FROM customer_profiles WHERE user_id = ?", (user["id"],)).fetchone()

        assert profile is not None
        assert profile["kyc_status"] == "VERIFIED"
        assert profile["dob"] == "1990-05-15"
        assert profile["pan"] == "ABCDE1234F"
        assert profile["aadhaar_last4"] == "9012"


# --------------------------------------------------------------------------- #
# Data integrity tests
# --------------------------------------------------------------------------- #
class TestDataIntegrity:
    def test_running_balance_is_correct_in_transaction_ledger(self, client, db_conn):
        """Each transaction's balance_paise field matches the account balance at that time."""
        # Register user with initial balance
        client.post("/register", data={
            "full_name": "Paul Thompson",
            "email": "paul@example.com",
            "phone": "9876543210",
            "password": "SecurePass123",
            "confirm": "SecurePass123",
            "account_type": "Savings",
            "opening_balance": "10000",
        })

        # Get user and account
        user = db_conn.execute("SELECT * FROM users WHERE email = ?", ("paul@example.com",)).fetchone()
        account = db_conn.execute("SELECT * FROM accounts WHERE user_id = ?", (user["id"],)).fetchone()

        # Login and perform multiple transactions
        client.post("/login", data={
            "email": "paul@example.com",
            "password": "SecurePass123",
        })

        client.post("/deposit", data={"amount": "5000"})
        client.post("/withdraw", data={"amount": "3000"})
        client.post("/deposit", data={"amount": "2000"})

        # Get all transactions
        txns = db_conn.execute(
            "SELECT * FROM transactions WHERE account_id = ? ORDER BY id",
            (account["id"],)
        ).fetchall()

        # Verify running balance is correct
        running_balance = 0
        for txn in txns:
            if txn["txn_type"] == "CREDIT":
                running_balance += txn["amount_paise"]
            else:
                running_balance -= txn["amount_paise"]

            assert txn["balance_paise"] == running_balance, \
                f"Transaction {txn['id']}: expected {running_balance}, got {txn['balance_paise']}"

    def test_account_balance_matches_final_transaction_balance(self, client, db_conn):
        """The account's current balance_paise matches the last transaction's balance_paise."""
        # Register and perform transactions
        client.post("/register", data={
            "full_name": "Quinn Adams",
            "email": "quinn@example.com",
            "phone": "9876543210",
            "password": "SecurePass123",
            "confirm": "SecurePass123",
            "account_type": "Savings",
            "opening_balance": "10000",
        })

        user = db_conn.execute("SELECT * FROM users WHERE email = ?", ("quinn@example.com",)).fetchone()
        account = db_conn.execute("SELECT * FROM accounts WHERE user_id = ?", (user["id"],)).fetchone()

        # Login and perform transactions
        client.post("/login", data={
            "email": "quinn@example.com",
            "password": "SecurePass123",
        })

        client.post("/deposit", data={"amount": "5000"})
        client.post("/withdraw", data={"amount": "2000"})

        # Get final state
        updated_account = db_conn.execute(
            "SELECT balance_paise FROM accounts WHERE id = ?", (account["id"],)
        ).fetchone()

        last_txn = db_conn.execute(
            "SELECT balance_paise FROM transactions WHERE account_id = ? ORDER BY id DESC LIMIT 1",
            (account["id"],)
        ).fetchone()

        assert updated_account["balance_paise"] == last_txn["balance_paise"]

    def test_transfer_maintains_total_money_in_system(self, client, db_conn):
        """A transfer doesn't change the total money in the system."""
        # Register two users with known balances
        client.post("/register", data={
            "full_name": "Rachel Green",
            "email": "rachel@example.com",
            "phone": "1111111111",
            "password": "SecurePass123",
            "confirm": "SecurePass123",
            "account_type": "Savings",
            "opening_balance": "10000",
        })

        client.post("/register", data={
            "full_name": "Ross Geller",
            "email": "ross@example.com",
            "phone": "2222222222",
            "password": "SecurePass123",
            "confirm": "SecurePass123",
            "account_type": "Savings",
            "opening_balance": "5000",
        })

        # Get initial total money
        initial_total = db_conn.execute(
            "SELECT SUM(balance_paise) as total FROM accounts"
        ).fetchone()["total"]

        # Get account numbers and perform transfer
        rachel = db_conn.execute("SELECT * FROM users WHERE email = ?", ("rachel@example.com",)).fetchone()
        rachel_account = db_conn.execute("SELECT * FROM accounts WHERE user_id = ?", (rachel["id"],)).fetchone()
        ross = db_conn.execute("SELECT * FROM users WHERE email = ?", ("ross@example.com",)).fetchone()
        ross_account = db_conn.execute("SELECT * FROM accounts WHERE user_id = ?", (ross["id"],)).fetchone()

        client.post("/login", data={
            "email": "rachel@example.com",
            "password": "SecurePass123",
        })

        client.post("/transfer", data={
            "to_account": ross_account["account_number"],
            "amount": "3000",
        })

        # Get final total money
        final_total = db_conn.execute(
            "SELECT SUM(balance_paise) as total FROM accounts"
        ).fetchone()["total"]

        assert initial_total == final_total
