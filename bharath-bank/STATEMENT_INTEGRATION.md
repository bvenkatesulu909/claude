# Wiring up the Account-Statement Export (`statement_export.py`)

This is a drop-in module. To expose it, add **one import line** and **two routes**
to `app.py`, then add two links to `templates/transactions.html`. Nothing in
`statement_export.py` needs to change, and no existing code in `app.py` is modified.

---

## 1. Add the import

Put this next to the existing `import finance` line near the top of `app.py`:

```python
from statement_export import statement_rows, to_csv, to_printable_html
```

---

## 2. Add the two routes

Paste this block anywhere among the authenticated routes in `app.py`
(e.g. right after the existing `transactions()` view). Both reuse the app's own
`get_db()`, `login_required`, `get_primary_account()`, `session`, `BANK_NAME`,
`IFSC_CODE` and `BRANCH_NAME`, so there are no new dependencies.

The optional `?start=YYYY-MM-DD&end=YYYY-MM-DD` query parameters filter the
statement by date (a bare end date is automatically expanded to end-of-day inside
`statement_rows`).

```python
from flask import Response  # already have Flask imports; add Response to that import list


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
```

> Note: `Response` is the only new name from Flask. If you would rather not touch
> the existing `from flask import (...)` block, you can instead write
> `from flask import Response` on its own line — both work.

---

## 3. Add the "Download CSV / Print" links to `templates/transactions.html`

In `templates/transactions.html`, inside the `.filters` block (around line 10–14,
next to the All / Credits / Debits links), add:

```html
<a href="{{ url_for('statement_csv') }}">Download CSV</a>
<a href="{{ url_for('statement_print') }}" target="_blank">Print / PDF</a>
```

`Print / PDF` opens the printable HTML in a new tab; the page has a
"Print / Save as PDF" button (and the user can use the browser's own Print → Save
as PDF). To carry a date filter through, append query params, e.g.
`{{ url_for('statement_csv', start='2026-04-01', end='2026-07-08') }}`.

---

## 4. Quick verification

```bash
cd "C:/Users/User/OneDrive/Desktop/Claude code/bharath-bank"
PYTHONIOENCODING=utf-8 python statement_export.py   # runs the built-in smoke test
```

Then, after wiring the routes and logging in:

- `GET /statement.csv` downloads a CSV attachment.
- `GET /statement/print` shows the tricolour printable statement (Ctrl+P → Save as PDF).
- `GET /statement.csv?start=2026-07-01&end=2026-07-05` filters by date.
