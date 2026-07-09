# Admin Console — setup

A back-office admin panel for Bharath Bank of India, shipped as a self-contained
Flask Blueprint. It adds **no new dependencies** and does **not** modify any
existing file — you only need to register the blueprint.

## 1. Register the blueprint (one edit to `app.py`)

Add these two lines near the **bottom** of `app.py`, just **before** the
`if __name__ == "__main__":` block (i.e. after `app`, `get_db` and `fmt_inr`
are already defined — this order avoids a circular import):

```python
from admin import admin_bp
app.register_blueprint(admin_bp)
```

That is the only change required. `wsgi.py` (`from app import app, init_db`)
picks it up automatically, so nothing else needs editing for production.

## 2. Sign in

- Visit **`/admin/login`**.
- Default password: **`admin123`**
- Override it by setting the environment variable `BBI_ADMIN_PASS`:

```bash
# Windows (PowerShell)
$env:BBI_ADMIN_PASS = "your-strong-password"

# macOS / Linux
export BBI_ADMIN_PASS="your-strong-password"
```

Signing in sets `session['is_admin'] = True`; every admin route is guarded by
the `admin_required` decorator. Sign out at `/admin/logout`.

## 3. Routes

| URL | What it shows |
|-----|---------------|
| `/admin/login` · `/admin/logout` | Shared-password sign in / out |
| `/admin` | Dashboard: customer count, total balances, active deposits (count + value), active loans (count + outstanding), pending loan count |
| `/admin/customers` | Every customer with account number, balance, KYC status |
| `/admin/customer/<id>` | One customer's accounts, deposits, loans and recent transactions |
| `/admin/loans` | Full loan book; **Approve / Reject** buttons appear for any `PENDING` loan |

The console reuses the app's own `get_db()`, `fmt_inr` and the `inr` Jinja
filter, so it reads/writes the same `bank.db` and matches the site's styling.

> Note: the customer app currently auto-decides loans on application, so
> `PENDING` loans are rare. Manual approve/reject is supported anyway and simply
> updates `loans.status` (approve also sets `outstanding_paise = principal`).

## Blueprint object

- Import name: **`admin_bp`** (Blueprint name: `admin`, url_prefix `/admin`)
- Registration snippet: `from admin import admin_bp` then `app.register_blueprint(admin_bp)`
