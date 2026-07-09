"""
statement_export.py — self-contained account-statement export for Bharath Bank.

Pure / near-pure helpers that turn the `transactions` ledger into an exportable
account statement in two formats:

    * CSV               (spreadsheet / audit friendly)
    * printable HTML    (open in a browser and "Print to PDF")

The only impure function is `statement_rows`, which reads from an already-open
sqlite3 connection (the app's `get_db()` value). Everything else operates on
plain Python data structures, so the formatting logic is trivially unit-testable
and has no Flask / request dependency.

Money is stored as INTEGER paise everywhere in the app; here we render it as
rupees (paise / 100) with exactly two decimals.

Row dict shape returned by `statement_rows` (also what to_csv / to_printable_html
expect each item of `rows` to look like):

    {
        "date":          "2026-07-08 14:03:11",   # created_at
        "description":   "Cash deposit",
        "ref_no":        "BBI2607080012345",
        "txn_type":      "CREDIT" | "DEBIT",
        "amount_paise":  150000,
        "balance_paise": 150000,
        "category":      "DEPOSIT",
        "counterparty":  "Self",
    }

`account` may be a sqlite3.Row or a plain dict; it should expose
`account_number`, `ifsc` and (optionally) `account_type`.

`bank_meta` is a plain dict, e.g.:

    {
        "name":   "Bharath Bank of India",
        "ifsc":   "BBIN0001729",
        "branch": "Bharath Nagar Main Branch, Hyderabad",
        "period": "2026-04-01 to 2026-07-08",   # optional; derived from rows if absent
    }
"""

import io
import csv
import html


# --------------------------------------------------------------------------- #
# Small value helpers (pure)
# --------------------------------------------------------------------------- #
def _get(obj, key, default=""):
    """Read `key` from a sqlite3.Row OR a plain dict, tolerating absence."""
    try:
        val = obj[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if val is None else val


def rupees(paise):
    """Integer paise -> plain rupee string with 2 decimals, e.g. 150000 -> '1500.00'.

    Uses integer math so there is never any binary-float rounding drift.
    Negative values keep their sign (not normally needed, but safe).
    """
    paise = int(paise or 0)
    sign = "-" if paise < 0 else ""
    whole, frac = divmod(abs(paise), 100)
    return f"{sign}{whole}.{frac:02d}"


def rupees_symbol(paise):
    """Like `rupees` but prefixed with the rupee glyph, for HTML output."""
    return "₹" + rupees(paise)


def _period_label(rows, bank_meta):
    """Human statement period: explicit bank_meta['period'] wins, else min/max date."""
    period = bank_meta.get("period")
    if period:
        return period
    if not rows:
        return "No transactions"
    dates = [r.get("date", "") for r in rows if r.get("date")]
    if not dates:
        return "No transactions"
    return f"{min(dates)} to {max(dates)}"


def _totals(rows):
    """Return (total_debit_paise, total_credit_paise) across the rows."""
    debit = sum(int(r.get("amount_paise", 0)) for r in rows if r.get("txn_type") == "DEBIT")
    credit = sum(int(r.get("amount_paise", 0)) for r in rows if r.get("txn_type") == "CREDIT")
    return debit, credit


# --------------------------------------------------------------------------- #
# 1. Data access (the only impure function)
# --------------------------------------------------------------------------- #
def statement_rows(db, account_id, start=None, end=None):
    """Return a list of row dicts for `account_id`, oldest-first.

    `start` / `end` are optional strings compared directly against the stored
    `created_at` text (format 'YYYY-MM-DD HH:MM:SS'). Because that format sorts
    lexicographically the same way it sorts chronologically, a plain string
    comparison is a correct date filter.

    Convenience: if a bare date ('YYYY-MM-DD', length 10) is passed as `end`,
    it is expanded to the end of that day so the whole day is included.
    """
    query = "SELECT * FROM transactions WHERE account_id = ?"
    params = [account_id]

    if start:
        query += " AND created_at >= ?"
        params.append(start)
    if end:
        end_bound = end + " 23:59:59" if len(end) == 10 else end
        query += " AND created_at <= ?"
        params.append(end_bound)

    query += " ORDER BY id ASC"

    rows = []
    for t in db.execute(query, params).fetchall():
        rows.append({
            "date":          _get(t, "created_at"),
            "description":   _get(t, "description"),
            "ref_no":        _get(t, "ref_no"),
            "txn_type":      _get(t, "txn_type"),
            "amount_paise":  int(_get(t, "amount_paise", 0)),
            "balance_paise": int(_get(t, "balance_paise", 0)),
            "category":      _get(t, "category"),
            "counterparty":  _get(t, "counterparty"),
        })
    return rows


# --------------------------------------------------------------------------- #
# 2. CSV export (pure)
# --------------------------------------------------------------------------- #
def to_csv(rows, account, bank_meta):
    """Render `rows` as a CSV string.

    Layout:
        - a small header block (bank name, account number, IFSC, period)
        - a blank line
        - column headers: Date, Description, Ref No, Type, Debit, Credit, Balance
        - one line per transaction (debit amount in Debit column, credit in Credit)
        - a blank line + totals summary
    """
    buf = io.StringIO()
    writer = csv.writer(buf)

    acc_no = _get(account, "account_number")
    ifsc = _get(account, "ifsc") or bank_meta.get("ifsc", "")
    period = _period_label(rows, bank_meta)

    # --- header block ---
    writer.writerow([bank_meta.get("name", "Account Statement")])
    writer.writerow(["Account Number", acc_no])
    writer.writerow(["IFSC", ifsc])
    if _get(account, "account_type"):
        writer.writerow(["Account Type", _get(account, "account_type")])
    writer.writerow(["Statement Period", period])
    writer.writerow([])

    # --- column headers ---
    writer.writerow(["Date", "Description", "Ref No", "Type", "Debit", "Credit", "Balance"])

    # --- transaction rows ---
    for r in rows:
        is_debit = r.get("txn_type") == "DEBIT"
        debit = rupees(r["amount_paise"]) if is_debit else ""
        credit = rupees(r["amount_paise"]) if not is_debit else ""
        writer.writerow([
            r.get("date", ""),
            r.get("description", ""),
            r.get("ref_no", ""),
            r.get("txn_type", ""),
            debit,
            credit,
            rupees(r["balance_paise"]),
        ])

    # --- totals ---
    total_debit, total_credit = _totals(rows)
    writer.writerow([])
    writer.writerow(["", "", "", "Totals", rupees(total_debit), rupees(total_credit), ""])

    return buf.getvalue()


# --------------------------------------------------------------------------- #
# 3. Printable HTML export (pure)
# --------------------------------------------------------------------------- #
def to_printable_html(rows, account, bank_meta):
    """Render `rows` as a standalone, self-contained printable HTML document.

    All CSS is inline in a <style> block so the returned string can be served
    directly or saved to disk and opened in any browser, then printed to PDF.
    The header uses the Indian tricolour (saffron / white / green) with a navy
    accent, matching the bank's identity.
    """
    e = html.escape  # local alias

    bank_name = e(str(bank_meta.get("name", "Account Statement")))
    acc_no = e(str(_get(account, "account_number")))
    acc_type = e(str(_get(account, "account_type", "Savings Account")))
    ifsc = e(str(_get(account, "ifsc") or bank_meta.get("ifsc", "")))
    branch = e(str(bank_meta.get("branch", "")))
    period = e(str(_period_label(rows, bank_meta)))

    total_debit, total_credit = _totals(rows)
    net = total_credit - total_debit

    # --- table body rows ---
    body_parts = []
    if rows:
        for r in rows:
            is_debit = r.get("txn_type") == "DEBIT"
            debit_cell = rupees_symbol(r["amount_paise"]) if is_debit else ""
            credit_cell = rupees_symbol(r["amount_paise"]) if not is_debit else ""
            type_class = "debit" if is_debit else "credit"
            body_parts.append(
                "<tr>"
                f"<td class='date'>{e(str(r.get('date', '')))}</td>"
                f"<td class='desc'>{e(str(r.get('description', '')))}"
                + (f"<span class='cp'>{e(str(r.get('counterparty', '')))}</span>"
                   if r.get("counterparty") else "")
                + "</td>"
                f"<td class='ref'>{e(str(r.get('ref_no', '')))}</td>"
                f"<td class='type {type_class}'>{e(str(r.get('txn_type', '')))}</td>"
                f"<td class='num debit'>{debit_cell}</td>"
                f"<td class='num credit'>{credit_cell}</td>"
                f"<td class='num bal'>{rupees_symbol(r['balance_paise'])}</td>"
                "</tr>"
            )
    else:
        body_parts.append(
            "<tr><td colspan='7' class='empty'>No transactions for this period.</td></tr>"
        )
    body = "\n".join(body_parts)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Account Statement — {bank_name}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #1a1a1a; margin: 0; padding: 24px; background: #f4f4f6;
  }}
  .sheet {{
    max-width: 900px; margin: 0 auto; background: #fff;
    box-shadow: 0 1px 6px rgba(0,0,0,.12); border-radius: 8px; overflow: hidden;
  }}
  .tricolor {{ height: 8px; background: linear-gradient(
      to right, #ff9933 0 33.33%, #ffffff 33.33% 66.66%, #138808 66.66% 100%); }}
  header {{ padding: 22px 28px 14px; border-bottom: 2px solid #eee; }}
  header h1 {{ margin: 0; font-size: 22px; color: #000080; letter-spacing: .3px; }}
  header .branch {{ color: #555; font-size: 12.5px; margin-top: 3px; }}
  .meta {{
    display: flex; flex-wrap: wrap; gap: 6px 40px;
    padding: 14px 28px; background: #fafaff; font-size: 13px;
  }}
  .meta div span {{ color: #666; display: block; font-size: 11px;
    text-transform: uppercase; letter-spacing: .5px; }}
  .meta div b {{ font-size: 14px; color: #111; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  thead th {{
    background: #000080; color: #fff; text-align: left; padding: 9px 12px;
    font-weight: 600; font-size: 12px; letter-spacing: .3px;
  }}
  thead th.num {{ text-align: right; }}
  tbody td {{ padding: 8px 12px; border-bottom: 1px solid #eee; vertical-align: top; }}
  td.num {{ text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }}
  td.date, td.ref {{ color: #666; white-space: nowrap; font-size: 12px; }}
  td.desc .cp {{ display: block; color: #888; font-size: 11px; }}
  td.type {{ font-weight: 600; font-size: 11px; }}
  td.type.credit, td.num.credit {{ color: #138808; }}
  td.type.debit,  td.num.debit  {{ color: #c0392b; }}
  td.num.bal {{ color: #111; font-weight: 600; }}
  td.empty {{ text-align: center; color: #999; padding: 28px; }}
  tbody tr:nth-child(even) td {{ background: #fbfbfd; }}
  .totals {{
    display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 34px;
    padding: 16px 28px; border-top: 2px solid #000080; background: #fafaff;
    font-size: 13px;
  }}
  .totals div span {{ color: #666; display: block; font-size: 11px;
    text-transform: uppercase; letter-spacing: .5px; }}
  .totals .t-debit b {{ color: #c0392b; }}
  .totals .t-credit b {{ color: #138808; }}
  .totals b {{ font-size: 15px; }}
  footer {{ padding: 14px 28px 22px; color: #888; font-size: 11px; line-height: 1.5; }}
  .print-btn {{
    display: inline-block; margin: 0 auto 18px; padding: 9px 18px; cursor: pointer;
    background: #000080; color: #fff; border: 0; border-radius: 6px; font-size: 13px;
  }}
  .toolbar {{ text-align: center; padding-top: 18px; }}
  @media print {{
    body {{ background: #fff; padding: 0; }}
    .sheet {{ box-shadow: none; border-radius: 0; max-width: none; }}
    .toolbar {{ display: none; }}
  }}
</style>
</head>
<body>
  <div class="toolbar">
    <button class="print-btn" onclick="window.print()">Print / Save as PDF</button>
  </div>
  <div class="sheet">
    <div class="tricolor"></div>
    <header>
      <h1>{bank_name}</h1>
      <div class="branch">{branch}</div>
    </header>
    <div class="meta">
      <div><span>Account Number</span><b>{acc_no}</b></div>
      <div><span>Account Type</span><b>{acc_type}</b></div>
      <div><span>IFSC</span><b>{ifsc}</b></div>
      <div><span>Statement Period</span><b>{period}</b></div>
    </div>
    <table>
      <thead>
        <tr>
          <th>Date</th><th>Description</th><th>Ref No</th><th>Type</th>
          <th class="num">Debit</th><th class="num">Credit</th><th class="num">Balance</th>
        </tr>
      </thead>
      <tbody>
{body}
      </tbody>
    </table>
    <div class="totals">
      <div class="t-debit"><span>Total Debits</span><b>{rupees_symbol(total_debit)}</b></div>
      <div class="t-credit"><span>Total Credits</span><b>{rupees_symbol(total_credit)}</b></div>
      <div class="t-net"><span>Net Change</span><b>{rupees_symbol(net)}</b></div>
    </div>
    <footer>
      This is a computer-generated statement and does not require a signature.
      Please verify all entries and report any discrepancy within 30 days.
      Generated by {bank_name} internet banking.
    </footer>
  </div>
</body>
</html>"""


# --------------------------------------------------------------------------- #
# Inline smoke test — run this file directly.
#   cd bharath-bank && PYTHONIOENCODING=utf-8 python statement_export.py
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    fake_rows = [
        {"date": "2026-07-01 09:15:00", "description": "Opening deposit",
         "ref_no": "BBI2607010000001", "txn_type": "CREDIT", "amount_paise": 5000000,
         "balance_paise": 5000000, "category": "DEPOSIT", "counterparty": "Self"},
        {"date": "2026-07-03 18:42:10", "description": "Grocery — SuperMart",
         "ref_no": "BBI2607030000042", "txn_type": "DEBIT", "amount_paise": 123450,
         "balance_paise": 4876550, "category": "WITHDRAWAL", "counterparty": "SuperMart"},
        {"date": "2026-07-05 11:05:33", "description": "Salary credit",
         "ref_no": "BBI2607050000108", "txn_type": "CREDIT", "amount_paise": 8500000,
         "balance_paise": 13376550, "category": "TRANSFER", "counterparty": "Acme Corp"},
    ]
    fake_account = {
        "account_number": "172988776655",
        "account_type": "Savings Account",
        "ifsc": "BBIN0001729",
    }
    bank_meta = {
        "name": "Bharath Bank of India",
        "ifsc": "BBIN0001729",
        "branch": "Bharath Nagar Main Branch, Hyderabad",
        "period": "2026-07-01 to 2026-07-08",
    }

    csv_text = to_csv(fake_rows, fake_account, bank_meta)
    # Use 'Rs.' in stdout (not the rupee glyph) to avoid Windows console encoding errors.
    print("=== CSV OUTPUT (amounts are plain rupees, e.g. Rs. 1500.00) ===")
    print(csv_text)

    html_text = to_printable_html(fake_rows, fake_account, bank_meta)
    assert isinstance(html_text, str), "to_printable_html must return a string"
    assert "<table" in html_text, "printable HTML must contain a <table"
    print("=== HTML OUTPUT CHECK ===")
    print("to_printable_html returned a string of length", len(html_text))
    print("contains '<table':", "<table" in html_text)
    print("OK - all checks passed.")
