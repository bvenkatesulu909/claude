"""
Bharath Bank of India — financial mathematics.

Pure functions, no I/O. Every amount is an INTEGER number of paise so there is
no floating-point money drift; intermediate growth factors use float and are
rounded back to paise only at the boundary.

Conventions (typical Indian retail banking):
  * Fixed Deposit  — quarterly compounding.
  * Recurring Deposit — monthly installments, interest compounded quarterly
    (expressed as an equivalent monthly effective rate).
  * Loans — EMI on a reducing balance (monthly rest).

Run `python finance.py` to print worked examples used to sanity-check the math.
"""

from datetime import date


# --------------------------------------------------------------------------- #
# Deposits
# --------------------------------------------------------------------------- #
def fd_maturity_paise(principal_paise, annual_rate_pct, tenure_months):
    """Fixed Deposit maturity value with quarterly compounding.

    A = P * (1 + r/400) ** (tenure_months / 3)
    (r/4 % per quarter; there are tenure_months/3 quarters.)
    """
    principal_paise = int(principal_paise)
    quarters = tenure_months / 3.0
    factor = (1.0 + annual_rate_pct / 400.0) ** quarters
    return int(round(principal_paise * factor))


def _rd_monthly_rate(annual_rate_pct):
    """Monthly effective rate equivalent to quarterly compounding."""
    return (1.0 + annual_rate_pct / 400.0) ** (1.0 / 3.0) - 1.0


def rd_maturity_paise(installment_paise, annual_rate_pct, tenure_months):
    """Recurring Deposit maturity value.

    One installment R is paid at the start of each of `n` months and each
    installment then compounds at the monthly effective rate i until maturity:

        M = R * (1+i) * ((1+i)^n - 1) / i

    (first installment earns interest for n months, ... last for 1 month).
    """
    installment_paise = int(installment_paise)
    n = int(tenure_months)
    i = _rd_monthly_rate(annual_rate_pct)
    if i == 0:
        return installment_paise * n
    factor = (1.0 + i) * ((1.0 + i) ** n - 1.0) / i
    return int(round(installment_paise * factor))


# --------------------------------------------------------------------------- #
# Loans (EMI, reducing balance)
# --------------------------------------------------------------------------- #
def loan_emi_paise(principal_paise, annual_rate_pct, tenure_months):
    """Equated Monthly Installment on a reducing balance.

    EMI = P * i * (1+i)^n / ((1+i)^n - 1),  i = monthly rate = r/1200.
    """
    principal_paise = int(principal_paise)
    n = int(tenure_months)
    i = annual_rate_pct / 1200.0
    if n <= 0:
        raise ValueError("Tenure must be at least one month.")
    if i == 0:
        return int(round(principal_paise / n))
    x = (1.0 + i) ** n
    emi = principal_paise * i * x / (x - 1.0)
    return int(round(emi))


def emi_split(outstanding_paise, annual_rate_pct, emi_paise):
    """Split one EMI on the current outstanding into (interest, principal, pay,
    new_outstanding). The final EMI is trued-up so the balance closes at zero.
    """
    outstanding_paise = int(outstanding_paise)
    i = annual_rate_pct / 1200.0
    interest = int(round(outstanding_paise * i))
    principal = emi_paise - interest
    if principal >= outstanding_paise:          # final (or over-) payment
        principal = outstanding_paise
        pay = interest + principal
    else:
        pay = emi_paise
    new_outstanding = outstanding_paise - principal
    return interest, principal, pay, new_outstanding


def amortization_schedule(principal_paise, annual_rate_pct, tenure_months, emi_paise=None):
    """Full amortization table. Returns a list of dicts, one per EMI."""
    if emi_paise is None:
        emi_paise = loan_emi_paise(principal_paise, annual_rate_pct, tenure_months)
    outstanding = int(principal_paise)
    rows = []
    for k in range(1, int(tenure_months) + 1):
        interest, principal, pay, outstanding = emi_split(outstanding, annual_rate_pct, emi_paise)
        rows.append({
            "emi_no": k,
            "emi_paise": pay,
            "interest_paise": interest,
            "principal_paise": principal,
            "outstanding_paise": outstanding,
        })
        if outstanding <= 0:
            break
    return rows


def loan_totals(principal_paise, annual_rate_pct, tenure_months):
    """(emi, total_payable, total_interest) for a loan."""
    emi = loan_emi_paise(principal_paise, annual_rate_pct, tenure_months)
    schedule = amortization_schedule(principal_paise, annual_rate_pct, tenure_months, emi)
    total_payable = sum(r["emi_paise"] for r in schedule)
    return emi, total_payable, total_payable - int(principal_paise)


# --------------------------------------------------------------------------- #
# Dates
# --------------------------------------------------------------------------- #
def add_months(d, months):
    """Return date `d` advanced by `months` months (clamping day-of-month)."""
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    month_index = d.month - 1 + int(months)
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    # clamp day to last valid day of the target month
    days_in_month = [31, 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28,
                     31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    day = min(d.day, days_in_month[month - 1])
    return date(year, month, day)


# --------------------------------------------------------------------------- #
# Worked examples / self-check
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    def rupees(p):
        return f"Rs.{p/100:,.2f}"

    print("== Fixed Deposit (quarterly compounding) ==")
    for p, r, m in [(10000000, 7.0, 12), (10000000, 7.0, 60), (50000000, 7.5, 24)]:
        print(f"  P={rupees(p)} @ {r}% for {m}m -> maturity {rupees(fd_maturity_paise(p, r, m))}")

    print("== Recurring Deposit ==")
    for inst, r, m in [(500000, 6.5, 12), (500000, 6.5, 60)]:
        mat = rd_maturity_paise(inst, r, m)
        print(f"  R={rupees(inst)}/m @ {r}% for {m}m -> invested {rupees(inst*m)}, maturity {rupees(mat)}")

    print("== Loan EMI (reducing balance) ==")
    for p, r, m in [(10000000, 11.5, 12), (500000000, 8.5, 240), (2000000, 9.5, 36)]:
        emi, total, interest = loan_totals(p, r, m)
        print(f"  P={rupees(p)} @ {r}% for {m}m -> EMI {rupees(emi)}, "
              f"total {rupees(total)}, interest {rupees(interest)}")

    print("== add_months ==")
    print("  2026-01-31 + 1m =", add_months("2026-01-31", 1))
    print("  2026-07-08 + 60m =", add_months("2026-07-08", 60))
