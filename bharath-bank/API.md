# API / Route Reference

Every route defined in `app.py`, in source order. "Auth" = requires an
active session (the `@login_required` decorator, which redirects to
`/login` with a flash message if `session["user_id"]` is missing). All
routes return server-rendered HTML (Jinja2 templates) unless noted as
JSON. **21 routes** in total.

## Public pages (no login required)

| Method(s) | Path | View function | Purpose |
|---|---|---|---|
| GET | `/` | `index` | Public landing page (`index.html`). |
| GET, POST | `/register` | `register` | Registration form. On POST: validates name/email/phone/password (password ≥ 6 chars, must match confirmation), rejects duplicate emails, creates the `users` row (hashed password), auto-generates a 12-digit `account_number` + creates the `accounts` row, optionally posts an opening-deposit `CREDIT` transaction if an opening balance > 0 was given, logs the new user in (`session["user_id"]`), and redirects to `/dashboard`. |
| GET, POST | `/login` | `login` | Login form. On POST: looks up the user by email and checks the password hash; on success clears/sets the session and redirects to `/dashboard`; on failure flashes "Invalid email or password." |
| GET | `/logout` | `logout` | Clears the session and redirects to `/` with a flash message. |
| GET | `/products` | `products` | Public catalogue page — lists all rows from `schemes` (ordered FD → RD → SAVINGS → other, then by rate descending) and all rows from `loan_products` (ordered by rate ascending). No login needed; this is the bank's public rates page. |

## Authenticated pages (require login)

| Method(s) | Path | View function | Purpose |
|---|---|---|---|
| GET | `/dashboard` | `dashboard` | Landing page after login: primary account, last 5 transactions, portfolio summary (`portfolio_summary()` — active deposit count/invested/maturity and active loan count/outstanding), and KYC profile. |
| GET, POST | `/deposit` | `deposit` | Cash deposit into the user's primary account. On POST: converts the entered rupee amount to paise, posts a `CREDIT` transaction with category `DEPOSIT`, flashes success, redirects to `/dashboard`. |
| GET, POST | `/withdraw` | `withdraw` | Cash withdrawal. On POST: re-reads the current balance, rejects if the amount exceeds it ("Insufficient balance for this withdrawal."), otherwise posts a `DEBIT` transaction with category `WITHDRAWAL`. |
| GET, POST | `/transfer` | `transfer` | Transfer funds to another BBI account by account number. On POST: resolves the payee by `account_number`, rejects unknown payees, rejects transferring to your own account, re-checks the sender's balance, then posts two linked ledger entries sharing one `ref_no` — a `DEBIT` (category `TRANSFER`) on the sender and a `CREDIT` (category `TRANSFER`) on the payee — committed together atomically. |
| GET | `/transactions` | `transactions` | Statement page for the primary account. Optional query param `?type=CREDIT` or `?type=DEBIT` filters the list (anything else, including absent, shows all); ordered newest-first. |
| GET | `/profile` | `profile` | Read-only view of the account and KYC profile. |
| GET, POST | `/kyc` | `kyc` | Account-holder / KYC form. On POST: validates the annual income field, upserts the `customer_profiles` row (`INSERT ... ON CONFLICT(user_id) DO UPDATE`) with DOB, gender, address, city, state, pincode, PAN (uppercased), last-4 Aadhaar digits, occupation, annual income (paise), nominee name/relation, and `updated_at`; `kyc_status` becomes `VERIFIED` once DOB, address, PAN, Aadhaar-last-4, and annual income are all present, otherwise stays `PENDING`. |

## Deposits (Fixed & Recurring) — authenticated

| Method(s) | Path | View function | Purpose |
|---|---|---|---|
| GET | `/deposits` | `deposits_page` | Lists the user's deposits (`deposits` table) plus the portfolio summary. |
| GET, POST | `/deposits/open` | `open_deposit` | Open a new FD or RD. GET shows only `schemes` where `openable = 1`. On POST: validates the chosen scheme code, amount, and tenure against the scheme's min/max tenure and minimum amount, checks the savings balance covers the amount, computes maturity via `finance.fd_maturity_paise` (FD) or `finance.rd_maturity_paise` (RD), debits the account (category = `FD` or `RD`), and inserts the `deposits` row (`installments_paid` starts at 1 for RD, since the first installment is collected immediately). |
| POST | `/deposits/<int:dep_id>/pay` | `pay_rd` | Pay the next monthly installment on an active RD. Validates the deposit belongs to the user, is an RD, is `ACTIVE`, and isn't already fully paid; checks the savings balance covers the installment (`principal_paise` on the deposit row); debits the account (category `RD`) and increments `installments_paid`. |
| POST | `/deposits/<int:dep_id>/close` | `close_deposit` | Close a deposit. If today's date is on/after `maturity_date`, credits the full projected `maturity_paise` and sets status `MATURED`; otherwise credits only the principal paid in so far (no interest) and sets status `CLOSED`. |

## Loans — authenticated

| Method(s) | Path | View function | Purpose |
|---|---|---|---|
| GET | `/loans` | `loans_page` | Lists the user's loans plus the full `loan_products` catalogue and their KYC profile. |
| GET, POST | `/loans/apply` | `apply_loan` | Apply for a loan. Requires KYC (specifically `annual_income_paise`) to be on file first — redirects to `/kyc` if missing. On POST: validates the chosen product, amount, and tenure (amount within `[min_amount_paise, max_amount_paise]`, tenure within `[6, max_tenure_months]`); computes `emi`/`total_payable`/`total_interest` via `finance.loan_totals`; runs the **FOIR check** (EMI must be ≤ 55% of `annual_income_paise / 12`); if all checks pass the loan is instantly `ACTIVE` — the principal is credited to the account and the processing fee (if any) is debited — otherwise it's instantly `REJECTED` with the failure reason(s) recorded in `decision_reason`. Either way, a row is inserted into `loans` with a generated `loan_account` (`BBILN` + 8 digits). |
| GET | `/loans/<int:loan_id>` | `loan_detail` | Loan detail page: the loan row, and — if status is `ACTIVE` or `CLOSED` — the full projected amortization schedule (`finance.amortization_schedule`) plus the actual `loan_payments` history. 404s if the loan doesn't exist or doesn't belong to the current user. |
| POST | `/loans/<int:loan_id>/pay` | `pay_emi` | Pay the next EMI on an active loan. Computes the interest/principal split against the loan's *current* `outstanding_paise` via `finance.emi_split` (which trues up the final payment so the loan closes at exactly zero); rejects if the account balance can't cover the payment amount; debits the account (category `LOAN`), inserts a `loan_payments` row, and updates `outstanding_paise` / `emis_paid` / `status` on the loan (flips to `CLOSED` once `outstanding_paise` reaches zero). |

## JSON API

| Method(s) | Path | View function | Auth | Purpose |
|---|---|---|---|---|
| GET | `/api/balance` | `api_balance` | Session (login required) | Returns the current user's primary account balance as JSON: `{"account_number": "...", "ifsc": "...", "balance": <rupees, float>, "currency": "INR"}`. Note `balance` is converted from `balance_paise` back to rupees (`/ 100`) for the JSON response — the only place in the app where paise is exposed as a float, for external/display convenience. |

### Example

```bash
curl -b cookies.txt http://127.0.0.1:5055/api/balance
```

```json
{
  "account_number": "172934815029",
  "ifsc": "BBIN0001729",
  "balance": 15250.75,
  "currency": "INR"
}
```

(A valid Flask session cookie from `/login` is required — there is no
token/API-key auth; this endpoint reuses the same cookie-based session as
the HTML pages.)

## Route summary by auth requirement

| Auth required | Count | Routes |
|---|---|---|
| Public | 5 | `/`, `/register`, `/login`, `/logout`, `/products` |
| Login required | 16 | `/dashboard`, `/deposit`, `/withdraw`, `/transfer`, `/transactions`, `/profile`, `/kyc`, `/deposits`, `/deposits/open`, `/deposits/<id>/pay`, `/deposits/<id>/close`, `/loans`, `/loans/apply`, `/loans/<id>`, `/loans/<id>/pay`, `/api/balance` |
| **Total** | **21** | |
