# Security Hardening Report — Bharath Bank of India (demo)

Scope: `app.py`, `finance.py`, and `templates/` in `bharath-bank/`.
Method: every claim below was verified against the actual source (line numbers cited).
Nothing in the app was modified — this document only describes the issues and the patches to apply.

## Summary

| Severity | Count | Issues |
|----------|-------|--------|
| Critical | 1 | Predictable `SECRET_KEY` fallback + `debug=True` |
| High     | 2 | Missing CSRF on all state-changing POSTs; unvalidated float amounts (`inf`→500, huge values) |
| Medium   | 3 | Session fixation on `register()`; TOCTOU / double-spend on balance updates; KYC PAN/Aadhaar not validated |
| Low      | 1 | Negative/zero tenure not explicitly rejected |
| Verified safe (no action) | 2 | KYC upsert SQL (parameterized); IDOR scoping on per-object routes |

**Top 3 to fix first**
1. **CRITICAL** — Require `BBI_SECRET` from the environment (never ship the hardcoded fallback) and turn off `debug=True` in production. A predictable secret key lets anyone forge a session cookie and take over any account.
2. **HIGH** — Add CSRF tokens to every state-changing POST form (helper + context processor + `before_request` guard). Money-moving routes are currently forgeable cross-site.
3. **HIGH** — Harden `rupees_to_paise()` (reject non-finite, cap a maximum) and apply the same to `register()` opening balance and `kyc()` income; `"inf"` currently raises an *uncaught* `OverflowError` → HTTP 500 with a full traceback under `debug=True`.

---

# CRITICAL

## C1. Predictable hardcoded `SECRET_KEY` fallback (+ `debug=True` in production)

- **File / location:** `app.py:38` (secret key), `app.py:1083` (`debug=True`)
- **Risk:** The session cookie is signed with `SECRET_KEY`. If `BBI_SECRET` is not set in the environment, the app silently falls back to the well-known literal `"bharath-bank-dev-secret-change-me"`. Anyone who knows (or reads this source for) that string can forge a signed session cookie — e.g. `{"user_id": 1}` — and log in as **any** user without credentials. That is full authentication bypass / account takeover. Separately, `app.run(debug=True)` enables the Werkzeug interactive debugger; if the app is ever reachable off-localhost, an unhandled exception (see H3) exposes a traceback and a Python console (remote code execution).
- **Patch:** Fail closed when the secret is absent in production, and gate the debugger on an explicit env flag.

Before (`app.py:38`):
```python
app.config["SECRET_KEY"] = os.environ.get("BBI_SECRET", "bharath-bank-dev-secret-change-me")
```

After:
```python
_secret = os.environ.get("BBI_SECRET")
if not _secret:
    if os.environ.get("BBI_ENV") == "production":
        raise RuntimeError("BBI_SECRET must be set in production.")
    _secret = "bharath-bank-dev-secret-change-me"   # dev-only convenience
app.config["SECRET_KEY"] = _secret

# Harden the session cookie while we are here.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("BBI_ENV") == "production",
)
```

Before (`app.py:1083`):
```python
    app.run(host="127.0.0.1", port=port, debug=True)
```

After:
```python
    app.run(host="127.0.0.1", port=port,
            debug=os.environ.get("BBI_ENV") != "production")
```

---

# HIGH

## H1. No CSRF protection on any state-changing POST route

- **File / location:** every POST form in `templates/`; routes in `app.py` (`register`, `login`, `deposit`, `withdraw`, `transfer`, `kyc`, `open_deposit`, `pay_rd`, `close_deposit`, `apply_loan`, `pay_emi`). No token is generated, embedded, or validated anywhere.
- **Risk:** A logged-in victim who visits an attacker page can have a hidden auto-submitting form move their money (`/transfer`, `/withdraw`), open deposits, pay EMIs, or overwrite KYC — all without their knowledge. Modern browsers' default `SameSite=Lax` gives *partial* protection against cross-site POST, but the app sets no `SameSite` attribute and must not rely on browser defaults for money movement. This is the standard defense-in-depth expectation for a banking app.
- **Approach (no new dependency):** a per-session random token stored in `session`, injected into every form via a context-processor helper, and validated for every POST in a `before_request` guard. Uses only the standard library (`secrets`, `hmac`) plus `markupsafe` (already a Flask dependency).

### Patch part 1 — helpers + guard (`app.py`)

Add to the imports near the top (`app.py:12-22`):
```python
import hmac
import secrets
from markupsafe import Markup
```

Add these helpers (anywhere after `app = Flask(__name__)`, e.g. just below the config block):
```python
# --------------------------------------------------------------------------- #
# CSRF protection (lightweight, standard-library only)
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
    if request.method == "POST":
        sent = request.form.get("_csrf_token", "")
        expected = session.get("_csrf_token", "")
        if not (expected and hmac.compare_digest(str(sent), str(expected))):
            abort(400, description="Invalid or missing CSRF token.")
```

### Patch part 2 — expose `csrf_field` to templates (`app.py:336-345`)

Before:
```python
@app.context_processor
def inject_globals():
    return {
        "BANK_NAME": BANK_NAME,
        "BANK_SHORT": BANK_SHORT,
        "IFSC_CODE": IFSC_CODE,
        "BRANCH_NAME": BRANCH_NAME,
        "current_user": get_current_user(),
        "year": datetime.now().year,
    }
```

After (one added key):
```python
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
```

### Patch part 3 — add `{{ csrf_field() }}` to EVERY POST form

Because the `before_request` guard rejects **all** POSTs without a valid token, every form below must include the field (including `login` and `register`). Insert `{{ csrf_field() }}` on its own line immediately after the opening `<form ...>` tag. All 12 forms across 11 templates:

| # | Template : line | Form action | Insert after the `<form>` tag |
|---|-----------------|-------------|-------------------------------|
| 1 | `register.html:8` | register | `{{ csrf_field() }}` |
| 2 | `login.html:8` | login | `{{ csrf_field() }}` |
| 3 | `deposit.html:8` | deposit | `{{ csrf_field() }}` |
| 4 | `withdraw.html:8` | withdraw | `{{ csrf_field() }}` |
| 5 | `transfer.html:8` | transfer | `{{ csrf_field() }}` |
| 6 | `kyc.html:9` | kyc | `{{ csrf_field() }}` |
| 7 | `open_deposit.html:8` | open_deposit | `{{ csrf_field() }}` |
| 8 | `apply_loan.html:16` | apply_loan | `{{ csrf_field() }}` |
| 9 | `loans.html:42` | pay_emi | `{{ csrf_field() }}` |
| 10 | `loan_detail.html:36` | pay_emi | `{{ csrf_field() }}` |
| 11 | `deposits.html:50` | pay_rd | `{{ csrf_field() }}` |
| 12 | `deposits.html:54` | close_deposit | `{{ csrf_field() }}` |

Concrete example — standard form (`deposit.html:8`):
```html
    <form method="post">
      {{ csrf_field() }}
```

Concrete example — inline action forms (`deposits.html:50-56`):
```html
      <form method="post" action="{{ url_for('pay_rd', dep_id=d.id) }}">
        {{ csrf_field() }}
        <button class="btn btn-primary" type="submit">Pay installment ({{ d.principal_paise | inr }})</button>
      </form>
      {% endif %}
      <form method="post" action="{{ url_for('close_deposit', dep_id=d.id) }}"
            onsubmit="return confirm('Close this deposit and credit the proceeds to your savings account?')">
        {{ csrf_field() }}
        <button class="btn btn-light" type="submit">Close / withdraw</button>
      </form>
```

Concrete example — form with extra attributes (`loan_detail.html:36`):
```html
    <form method="post" action="{{ url_for('pay_emi', loan_id=loan.id) }}" style="margin-top:6px">
      {{ csrf_field() }}
      <button class="btn btn-primary btn-block" type="submit">Pay next EMI · {{ loan.emi_paise | inr }}</button>
    </form>
```

> Note: `session.clear()` on login/logout/register (and the fix in M1) drops the token; a fresh one is minted automatically the next time a page renders a form, so no user-visible breakage.

## H2. Unvalidated float amounts — `inf` → HTTP 500, and huge values create absurd balances

- **File / location:** `rupees_to_paise()` `app.py:269-274`; same pattern duplicated in `register()` `app.py:445-448` (opening balance) and `kyc()` `app.py:658` (annual income).
- **Risk (verified behavior):**
  - `float("nan")` → `round(nan*100)` raises **`ValueError`** — it *is* caught by the callers' `except ValueError`, but the raw message `"cannot convert float NaN to integer"` is flashed to the user (internal detail leak).
  - `float("inf")` (and `"-inf"`, `"1e400"`, `"1e308"`) → `round(inf*100)` raises **`OverflowError`**, which is **not** caught by the routes' `except ValueError` → unhandled 500. Under `debug=True` (C1) this returns a full traceback / interactive debugger.
  - Large **finite** values such as `"1e15"` / `"1e18"` pass through silently and produce absurd amounts (₹10 trillion+). `/deposit` applies the credit with no upper bound, so a user can inflate their own balance arbitrarily.
  - (The task's premise that `inf`/`nan` "pass round()" is not quite right — they raise; the real "absurd amount" vector is large *finite* input. The patch closes all three.)
- **Patch — `rupees_to_paise()`** (`app.py:269-274`)

Add to imports (`app.py:12`):
```python
import math
```

Before:
```python
def rupees_to_paise(value):
    """Accepts a string/number of rupees and returns integer paise. Raises ValueError."""
    amount = round(float(value) * 100)
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    return int(amount)
```

After:
```python
# ₹10,00,00,000 (₹10 crore) per-transaction ceiling for this demo. Tune as needed.
MAX_TXN_PAISE = 100_00_00_000


def rupees_to_paise(value):
    """Accepts a string/number of rupees and returns integer paise. Raises ValueError."""
    rupees = float(value)                       # non-numeric -> ValueError (handled by callers)
    if not math.isfinite(rupees):               # reject nan / inf / -inf
        raise ValueError("Amount must be a finite number.")
    amount = round(rupees * 100)
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    if amount > MAX_TXN_PAISE:
        raise ValueError("Amount exceeds the per-transaction limit.")
    return int(amount)
```

- **Patch — `register()` opening balance** (`app.py:444-450`)

Before:
```python
            try:
                opening_val = float(opening)
                if opening_val < 0:
                    raise ValueError
                opening_paise = round(opening_val * 100)
            except ValueError:
                error = "Opening balance must be a valid non-negative amount."
```

After:
```python
            try:
                opening_val = float(opening)
                if not math.isfinite(opening_val) or opening_val < 0:
                    raise ValueError
                opening_paise = round(opening_val * 100)
                if opening_paise > MAX_TXN_PAISE:
                    raise ValueError
            except ValueError:
                error = "Opening balance must be a valid non-negative amount."
```

- **Patch — `kyc()` annual income** (`app.py:656-663`)

Before:
```python
        income_raw = f.get("annual_income", "").strip()
        try:
            income_paise = round(float(income_raw) * 100) if income_raw else None
            if income_paise is not None and income_paise < 0:
                raise ValueError
        except ValueError:
            flash("Annual income must be a valid amount.", "danger")
            return redirect(url_for("kyc"))
```

After:
```python
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
```

---

# MEDIUM

## M1. Session fixation in `register()`

- **File / location:** `app.py:483` — `session["user_id"] = user_id` is set **without** a prior `session.clear()`. (By contrast `login()` at `app.py:500` correctly clears first.)
- **Risk:** An attacker who can plant/fix a session cookie in the victim's browser before they register (e.g. via a shared machine or a cookie-injection vector) keeps that same session id after the victim authenticates, letting the attacker ride the now-authenticated session. Rotating the session on privilege change is the standard mitigation.
- **Patch:** `app.py:481-484`. Clear the session **before** `flash()` (flash messages are themselves stored in the session, so clearing after would wipe the welcome message).

Before:
```python
                db.commit()
                flash(f"Welcome to {BANK_NAME}! Your account number is {acc_number}.", "success")
                session["user_id"] = user_id
                return redirect(url_for("dashboard"))
```

After:
```python
                db.commit()
                session.clear()                 # rotate session id — prevent fixation
                session["user_id"] = user_id
                flash(f"Welcome to {BANK_NAME}! Your account number is {acc_number}.", "success")
                return redirect(url_for("dashboard"))
```

## M2. TOCTOU / double-spend on balance read-modify-write

- **File / location:** `_post_transaction()` `app.py:1049-1071`; balance pre-checks in `withdraw` (`app.py:562-567`), `transfer` (`app.py:601-606`), `open_deposit` (`app.py:762-766`), `pay_rd` (`app.py:817-822`), `pay_emi` (`app.py:1000-1006`).
- **Risk:** Balance is read into Python, checked (`amount > balance`), then `_post_transaction` re-reads and writes `balance ± amount`. This is a read-modify-write with no atomicity or row guard. Two rapid concurrent submissions (double-click / scripted replay) can both pass the sufficiency check against the same starting balance and both debit — a classic double-spend / lost-update. SQLite serializes the *commits*, but because the new balance is computed in Python from a stale read, the second commit overwrites rather than accumulates.
- **Mitigation (demo-appropriate):** make the debit atomic and conditional at the SQL level so the database — not stale Python state — enforces the balance floor. This closes both the lost-update and the overdraft window in one statement.
- **Patch:** `_post_transaction()` `app.py:1052-1061`

Before:
```python
    db = get_db()
    row = db.execute(
        "SELECT balance_paise FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()
    balance = row["balance_paise"]
    balance = balance + amount_paise if txn_type == "CREDIT" else balance - amount_paise

    db.execute(
        "UPDATE accounts SET balance_paise = ? WHERE id = ?", (balance, account_id)
    )
```

After:
```python
    db = get_db()
    if txn_type == "CREDIT":
        db.execute(
            "UPDATE accounts SET balance_paise = balance_paise + ? WHERE id = ?",
            (amount_paise, account_id),
        )
    else:
        # Atomic guarded debit: only succeeds if funds are still sufficient,
        # closing the double-submit / lost-update race at the DB level.
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
```

> Trade-off note: with this change a debit that loses the race now raises `ValueError` instead of silently overdrawing. The route-level pre-checks remain as the friendly "Insufficient balance" flash for the common case; the guarded UPDATE is the authoritative backstop for the concurrent case. If you want the rare racing request to render a clean flash rather than surface an error, wrap the debit `_post_transaction(...)` calls in `try/except ValueError`. For a demo, leaving the pre-check + atomic guard is sufficient and prevents the overdraft.

## M3. KYC PAN / Aadhaar accepted without validation

- **File / location:** `kyc()` `app.py:672-673`
  - `pan=f.get("pan", "").strip().upper()` — stored verbatim, no format check.
  - `aadhaar_last4=f.get("aadhaar", "").strip()[-4:]` — **confirmed:** only the last 4 characters are ever stored (correct data-minimization), but there is no check that the input is 12 digits, so `"abc"` stores `"abc"`, `""` stores `""`.
- **Risk:** Garbage identity values are accepted and, because `kyc()` sets `kyc_status = "VERIFIED"` when the identity fields are merely *non-empty* (`app.py:680-682`), a user can auto-"verify" KYC with junk PAN/Aadhaar and then become eligible for loans (`apply_loan` only checks that `annual_income_paise` is present). This is a data-integrity / KYC-bypass concern rather than a memory-safety issue.
- **Patch:** validate formats before building the `fields` dict. Insert immediately after the income block (around `app.py:664`, before `fields = dict(...)`):

```python
import re  # add near the top-level imports

        # --- KYC identity format validation ---
        pan = f.get("pan", "").strip().upper()
        aadhaar = f.get("aadhaar", "").strip()
        if pan and not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", pan):
            flash("PAN must be in the format ABCDE1234F.", "danger")
            return redirect(url_for("kyc"))
        if aadhaar and not re.fullmatch(r"[0-9]{12}", aadhaar):
            flash("Aadhaar must be exactly 12 digits.", "danger")
            return redirect(url_for("kyc"))
```

Then change the two lines inside the `fields = dict(...)` block (`app.py:672-673`) to reuse the validated values:

Before:
```python
            pan=f.get("pan", "").strip().upper(),
            aadhaar_last4=f.get("aadhaar", "").strip()[-4:],
```

After:
```python
            pan=pan,
            aadhaar_last4=aadhaar[-4:],
```

(`^...$` in the task is expressed here as `re.fullmatch`, which anchors both ends implicitly — equivalent to `^[A-Z]{5}[0-9]{4}[A-Z]$` and `^[0-9]{12}$`. Only the last 4 Aadhaar digits are still what gets stored.)

---

# LOW

## L1. Negative / zero tenure not explicitly rejected

- **File / location:** `open_deposit()` `app.py:747`, `apply_loan()` `app.py:895` — both do `int(request.form.get("tenure_months", ""))`. `int("-5")` returns `-5`.
- **Risk (low, mostly latent):** In practice a negative tenure is caught downstream — `open_deposit` rejects it against the scheme `min_tenure_months` (all openable schemes have one), and `apply_loan` rejects `tenure < 6`. So there is no live exploit today, but the guard relies on scheme/product config rather than validating the input itself; a future openable scheme with no `min_tenure_months` would pass a negative tenure into the finance math.
- **Patch (defense-in-depth):** reject non-positive tenure right where it is parsed.

`open_deposit()` — before (`app.py:745-750`):
```python
        try:
            amount = rupees_to_paise(request.form.get("amount", ""))
            tenure = int(request.form.get("tenure_months", ""))
        except ValueError:
            flash("Enter a valid amount and a whole number of months.", "danger")
            return redirect(url_for("open_deposit"))
```
After:
```python
        try:
            amount = rupees_to_paise(request.form.get("amount", ""))
            tenure = int(request.form.get("tenure_months", ""))
            if tenure <= 0:
                raise ValueError
        except ValueError:
            flash("Enter a valid amount and a whole number of months.", "danger")
            return redirect(url_for("open_deposit"))
```

Apply the identical `if tenure <= 0: raise ValueError` inside the corresponding `try` in `apply_loan()` (`app.py:893-898`).

---

# VERIFIED SAFE — no action required

## S1. KYC upsert SQL — NOT injectable (VERDICT: SAFE)

- **File / location:** `kyc()` `app.py:685-693`.
- **Assessment:** The statement is assembled with f-strings:
  ```python
  cols = ", ".join(fields.keys())
  placeholders = ", ".join(["?"] * len(fields))
  updates = ", ".join(f"{k} = excluded.{k}" for k in fields)
  db.execute(f"INSERT INTO customer_profiles (user_id, {cols}) VALUES (?, {placeholders})"
             f" ON CONFLICT(user_id) DO UPDATE SET {updates}",
             [uid] + list(fields.values()))
  ```
  The interpolated tokens (`cols`, `updates`) come **only** from `fields.keys()`, which are hardcoded literal identifiers in the source (`dob`, `gender`, … `kyc_status`, `updated_at`). No user-controlled string ever reaches the SQL text. Every user-supplied **value** is bound through a `?` placeholder via `[uid] + list(fields.values())`. **Verdict: safe — no SQL injection.**
- **Other queries checked:** `transactions()` (`app.py:627-633`), `deposits_for`/`loans_for` (`app.py:367-384`) and `portfolio_summary` also concatenate only fixed literal fragments and bind all values with `?`. All parameterized. No string-formatted user input anywhere.

## S2. IDOR scoping on per-object routes (VERDICT: SAFE)

Each route that takes an object id from the URL scopes the lookup by the session user, so one customer cannot read or act on another's objects:

| Route | Location | Query | Verdict |
|-------|----------|-------|---------|
| `pay_rd(dep_id)` | `app.py:808-809` | `SELECT ... FROM deposits WHERE id = ? AND user_id = ?` | Scoped ✓ |
| `close_deposit(dep_id)` | `app.py:838-839` | `SELECT ... FROM deposits WHERE id = ? AND user_id = ?` | Scoped ✓ |
| `pay_emi(loan_id)` | `app.py:994-995` | `SELECT ... FROM loans WHERE id = ? AND user_id = ?` | Scoped ✓ |
| `loan_detail(loan_id)` | `app.py:974-977` | `SELECT ... FROM loans WHERE id = ? AND user_id = ?`, `abort(404)` if none | Scoped ✓ |

All four correctly filter by `user_id = session["user_id"]`. A non-owner id simply returns no row (flash / 404). **Verdict: no IDOR.** (Transfers look up the payee by public account number, which is intended, and the debit always targets the sender's own primary account.)

---

*End of report. No application files were modified.*
