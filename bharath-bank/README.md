# Bharath Bank of India

A full-stack **dummy internet-banking application** — Flask backend, SQLite
database, server-rendered Jinja2 templates. Built purely for demonstration
and learning purposes.

> **This is not a real bank.** It is not registered with the RBI, is not
> connected to any real banking, payment, or settlement network, and holds
> no real money. All account numbers, IFSC codes, interest rates, and
> customer data are fictional or self-registered demo data.

## Overview

Bharath Bank of India ("BBI") is a single-branch demo bank (branch:
*Bharath Nagar Main Branch, Hyderabad*, IFSC `BBIN0001729`). A visitor can
register, receive an auto-generated 12-digit account number, and then use
a full suite of retail-banking features — deposits, withdrawals,
inter-account transfers, term deposits (FD/RD), and loans with real-time
underwriting — all served from a single Flask app (`app.py`) backed by a
local SQLite file (`bank.db`).

## Features

| Area | What it does |
|---|---|
| **Accounts** | Self-service registration issues a unique 12-digit account number (prefixed `1729`) and the shared demo IFSC code. Optional opening deposit. |
| **Deposit / Withdraw** | Cash-in / cash-out on your own account, with balance re-checked at write time to prevent overdraws. |
| **Transfers** | Real double-entry transfer to any other BBI account by account number — debit and credit legs are written atomically in one DB transaction and share a single reference number. |
| **Transaction history** | Full statement per account with a running balance recorded on every ledger row, filterable by credit/debit. |
| **Fixed Deposits (FD)** | Lump-sum term deposit with **quarterly compounding**, projected maturity value and maturity date shown at booking time. |
| **Recurring Deposits (RD)** | Monthly-installment deposit; each installment is debited from savings on demand and maturity is projected using an effective monthly rate. |
| **Deposit closure** | Close a deposit early (principal only, no interest) or after maturity (full projected maturity value credited back to savings). |
| **Loans** | Personal / Home / Vehicle / Education / Gold loans with **reducing-balance EMI**, a full amortization schedule, and **instant, real-time eligibility** decisioning (FOIR 55% rule, amount/tenure bounds). |
| **EMI repayment** | Pay one EMI at a time; the ledger of principal/interest split and outstanding balance is kept per loan in `loan_payments`, and the final EMI is trued-up so the loan closes at exactly zero. |
| **KYC / account-holder info** | Personal details, PAN, Aadhaar (last 4 digits only), occupation, annual income, nominee — required before a loan application; status flips to `VERIFIED` once core identity fields are filled in. |
| **Products & rates** | Public, no-login page listing all deposit schemes and loan products with their live seeded interest rates. |
| **JSON API** | `GET /api/balance` — session-authenticated balance lookup for programmatic access. |

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3 + Flask |
| Database | SQLite via the standard-library `sqlite3` module (no ORM) — `bank.db`, created and seeded automatically on first run |
| Templates | Jinja2, server-rendered HTML (`templates/`) |
| Styling | Hand-written CSS (`static/style.css`) |
| Auth | Werkzeug `generate_password_hash` / `check_password_hash` + Flask server-side sessions (`SECRET_KEY` from `BBI_SECRET` env var) |
| Money | Every amount stored as an **integer number of paise** — no floats in the ledger |
| Production serving | Gunicorn (`wsgi.py`, `Procfile`, `render.yaml`) — see `DEPLOY.md` / `DOCKER.md` for hosting |

## Project layout

```
bharath-bank/
├── app.py              # Flask app: schema (init_db), seed data, routes, transaction engine
├── finance.py           # Pure financial math: FD/RD maturity, EMI, amortization
├── requirements.txt     # Flask, gunicorn
├── wsgi.py               # Gunicorn entry point
├── bank.db               # SQLite database file (auto-created)
├── static/
│   └── style.css
└── templates/
    ├── base.html                       # shared layout, nav, flash messages
    ├── index.html                      # public landing page
    ├── register.html · login.html
    ├── dashboard.html
    ├── deposit.html · withdraw.html · transfer.html · transactions.html
    ├── deposits.html · open_deposit.html
    ├── loans.html · apply_loan.html · loan_detail.html
    ├── profile.html · kyc.html
    └── products.html
```

## How to run locally

```bash
cd bharath-bank
pip install -r requirements.txt
python app.py
```

This calls `init_db()` (creates `bank.db` if missing and seeds the
`schemes` / `loan_products` reference tables), then starts the Flask dev
server. Open:

```
http://127.0.0.1:5055
```

The port defaults to **5055** and can be overridden with the `PORT`
environment variable. The session secret defaults to a hardcoded dev value
and can be overridden with `BBI_SECRET`.

For containerized or cloud deployment (Render, Railway, Docker), see
`DEPLOY.md` and `DOCKER.md` in this folder.

## Demo login

There is **no pre-seeded customer account** — the `users` table starts
empty. To try the app:

1. Go to `/register` and create an account (any name/email/password, with
   an optional opening balance). You'll land on the dashboard immediately
   with a freshly issued account number.
2. Register a second account (e.g. in a private/incognito window) to test
   **Transfer** between two BBI accounts.
3. Fill in **KYC** (`/kyc`) with a DOB, address, PAN, Aadhaar, and annual
   income before applying for a loan — the eligibility check needs your
   income to compute the FOIR limit.

Only the **reference data** is pre-seeded on first boot: the `schemes`
table (FD/RD/Savings/PPF/SCSS products) and `loan_products` table
(Personal/Home/Vehicle/Education/Gold), both visible on the public
`/products` page without logging in.

> On free-tier cloud hosting the SQLite file is typically ephemeral, so
> registered users/transactions reset on redeploy while the schemes/loan
> product catalogue simply re-seeds. See `DEPLOY.md` for details.

## Financial formulas

All money is handled as **integer paise**; the formulas below operate on
that integer principal/installment and round back to the nearest paisa
only at the end of each calculation (see `finance.py`).

### Fixed Deposit (FD) — quarterly compounding

```
A = P × (1 + r / 400) ^ (t / 3)
```

- `P` = principal (paise)
- `r` = annual interest rate (%)
- `t` = tenure in months (so `t / 3` = number of quarters)
- `r / 400` = the quarterly rate expressed as a fraction (`r/4` percent per quarter, i.e. `r/4/100`)
- `A` = maturity value (paise), rounded to the nearest integer

### Recurring Deposit (RD) — monthly installments, quarterly-equivalent compounding

First, the annual rate is converted to an **equivalent monthly effective
rate** `i` consistent with quarterly compounding:

```
i = (1 + r / 400) ^ (1/3) − 1
```

Then, with one installment `R` paid at the start of each of `n` months
(the first installment earns interest for all `n` months, the last for
just 1 month):

```
M = R × (1 + i) × ((1 + i)^n − 1) / i
```

- `R` = monthly installment (paise)
- `n` = tenure in months
- `M` = maturity value (paise)
- If `i = 0` (zero-rate edge case), `M = R × n`

### Loan EMI — reducing balance, monthly rests

```
i = r / 1200                      (monthly rate, r = annual % rate)
EMI = P × i × (1 + i)^n / ((1 + i)^n − 1)
```

- `P` = principal (paise), `n` = tenure in months, `EMI` rounded to the nearest paisa
- If `i = 0`, `EMI = P / n`

Each month, the EMI is split against the **current outstanding balance**:

```
interest_this_month = outstanding × i
principal_this_month = EMI − interest_this_month
new_outstanding = outstanding − principal_this_month
```

The final installment is trued up: if the computed principal portion
would exceed the remaining outstanding, the whole remaining outstanding is
charged as principal and the payment for that month becomes
`interest + remaining outstanding`, so the loan always closes at exactly
zero paise outstanding.

### Loan eligibility — FOIR (Fixed Obligation to Income Ratio)

At application time, the EMI computed from the requested amount/rate/
tenure is checked against the applicant's declared annual income (from
KYC):

```
monthly_income = annual_income / 12
EMI must be ≤ 0.55 × monthly_income
```

If the EMI would exceed 55% of monthly income, or the amount/tenure falls
outside the loan product's configured bounds, the application is
instantly rejected with a reason; otherwise it is instantly approved and
disbursed to the applicant's savings account (minus the product's
processing fee).

## Disclaimer

Bharath Bank of India is a fictional demonstration project created for
portfolio / educational purposes. It is **not a licensed bank**, is **not
affiliated with the Reserve Bank of India or any real financial
institution**, processes **no real payments**, and should never be used to
enter real personal, financial, or identity information.
