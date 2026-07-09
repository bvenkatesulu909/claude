"""Unit tests for finance.py — pure financial-maths functions, no Flask/DB.

Expected values for the "known case" tests are computed independently in this
file using the same documented formulas (quarterly-compounding FD, RD, and
reducing-balance EMI), then compared against finance.py's actual output. This
catches regressions in the implementation without simply re-testing itself.
"""
import os
import sys
from datetime import date

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import finance


# --------------------------------------------------------------------------- #
# Independent reference implementations (mirror the documented formulas)
# --------------------------------------------------------------------------- #
def _expected_fd_maturity(principal_paise, annual_rate_pct, tenure_months):
    quarters = tenure_months / 3.0
    factor = (1.0 + annual_rate_pct / 400.0) ** quarters
    return int(round(principal_paise * factor))


def _expected_rd_monthly_rate(annual_rate_pct):
    return (1.0 + annual_rate_pct / 400.0) ** (1.0 / 3.0) - 1.0


def _expected_rd_maturity(installment_paise, annual_rate_pct, tenure_months):
    n = int(tenure_months)
    i = _expected_rd_monthly_rate(annual_rate_pct)
    if i == 0:
        return installment_paise * n
    factor = (1.0 + i) * ((1.0 + i) ** n - 1.0) / i
    return int(round(installment_paise * factor))


def _expected_emi(principal_paise, annual_rate_pct, tenure_months):
    n = int(tenure_months)
    i = annual_rate_pct / 1200.0
    if i == 0:
        return int(round(principal_paise / n))
    x = (1.0 + i) ** n
    emi = principal_paise * i * x / (x - 1.0)
    return int(round(emi))


# --------------------------------------------------------------------------- #
# Fixed Deposit — quarterly compounding
# --------------------------------------------------------------------------- #
class TestFdMaturity:
    def test_known_case_1lakh_at_7pct_12m(self):
        principal = 100_00_00  # Rs 1,00,000 in paise -> 10,000,000
        principal = 10_000_000
        result = finance.fd_maturity_paise(principal, 7.0, 12)
        assert result == 10_718_590
        assert result == _expected_fd_maturity(principal, 7.0, 12)
        assert isinstance(result, int)

    def test_known_case_6_month_tenure(self):
        principal = 10_000_000
        result = finance.fd_maturity_paise(principal, 7.0, 6)
        assert result == _expected_fd_maturity(principal, 7.0, 6)

    def test_senior_citizen_rate_larger_principal(self):
        principal = 50_000_000  # Rs 5,00,000
        result = finance.fd_maturity_paise(principal, 7.5, 24)
        assert result == _expected_fd_maturity(principal, 7.5, 24)
        # sanity: maturity must exceed principal at a positive rate
        assert result > principal

    def test_zero_rate_returns_principal_unchanged(self):
        principal = 10_000_000
        assert finance.fd_maturity_paise(principal, 0.0, 12) == principal

    def test_tax_saver_five_year_tenure(self):
        principal = 10_000_000
        result = finance.fd_maturity_paise(principal, 7.25, 60)
        assert result == _expected_fd_maturity(principal, 7.25, 60)


# --------------------------------------------------------------------------- #
# Recurring Deposit
# --------------------------------------------------------------------------- #
class TestRdMaturity:
    def test_known_case_12_months(self):
        result = finance.rd_maturity_paise(500_000, 6.5, 12)
        assert result == _expected_rd_maturity(500_000, 6.5, 12)
        assert result == 6_214_323

    def test_known_case_five_year_tenure(self):
        result = finance.rd_maturity_paise(500_000, 6.5, 60)
        assert result == _expected_rd_maturity(500_000, 6.5, 60)
        assert result > 500_000 * 60  # interest must have accrued

    def test_zero_rate_equals_installments_times_months(self):
        result = finance.rd_maturity_paise(500_000, 0.0, 12)
        assert result == 500_000 * 12


# --------------------------------------------------------------------------- #
# Loan EMI (reducing balance)
# --------------------------------------------------------------------------- #
class TestLoanEmi:
    def test_known_case_personal_loan(self):
        result = finance.loan_emi_paise(10_000_000, 11.5, 12)
        assert result == 886_151
        assert result == _expected_emi(10_000_000, 11.5, 12)

    def test_zero_rate_evenly_divides_principal(self):
        assert finance.loan_emi_paise(12_000_000, 0.0, 12) == 1_000_000

    def test_one_month_tenure_equals_principal_plus_interest(self):
        principal = 10_000_000
        rate = 12.0
        emi = finance.loan_emi_paise(principal, rate, 1)
        expected_interest = round(principal * (rate / 1200.0))
        assert emi == principal + expected_interest

    def test_raises_for_zero_or_negative_tenure(self):
        with pytest.raises(ValueError):
            finance.loan_emi_paise(10_000_000, 10.0, 0)
        with pytest.raises(ValueError):
            finance.loan_emi_paise(10_000_000, 10.0, -3)


# --------------------------------------------------------------------------- #
# Amortization schedule
# --------------------------------------------------------------------------- #
class TestAmortizationSchedule:
    def test_principal_column_sums_exactly_and_outstanding_closes(self):
        principal = 10_000_000
        rate = 11.5
        months = 12
        schedule = finance.amortization_schedule(principal, rate, months)
        assert len(schedule) == months
        assert sum(row["principal_paise"] for row in schedule) == principal
        assert schedule[-1]["outstanding_paise"] == 0

    def test_long_tenure_home_loan_closes_exactly(self):
        principal = 500_000_000
        rate = 8.5
        months = 240
        schedule = finance.amortization_schedule(principal, rate, months)
        assert len(schedule) == months
        assert sum(row["principal_paise"] for row in schedule) == principal
        assert schedule[-1]["outstanding_paise"] == 0
        # outstanding must be monotonically non-increasing
        outstandings = [row["outstanding_paise"] for row in schedule]
        assert outstandings == sorted(outstandings, reverse=True)

    def test_zero_rate_one_month_tenure(self):
        principal = 500_000
        schedule = finance.amortization_schedule(principal, 0.0, 1)
        assert len(schedule) == 1
        assert schedule[0]["principal_paise"] == principal
        assert schedule[0]["interest_paise"] == 0
        assert schedule[0]["outstanding_paise"] == 0

    def test_explicit_emi_argument_is_honoured(self):
        principal = 10_000_000
        rate = 11.5
        months = 12
        emi = finance.loan_emi_paise(principal, rate, months)
        schedule = finance.amortization_schedule(principal, rate, months, emi)
        assert schedule[0]["emi_paise"] == emi


# --------------------------------------------------------------------------- #
# emi_split
# --------------------------------------------------------------------------- #
class TestEmiSplit:
    def test_interest_plus_principal_equals_pay(self):
        outstanding = 10_000_000
        rate = 11.5
        emi = finance.loan_emi_paise(outstanding, rate, 12)
        interest, principal, pay, new_outstanding = finance.emi_split(outstanding, rate, emi)
        assert interest + principal == pay
        assert new_outstanding == outstanding - principal

    def test_running_the_full_schedule_closes_balance_at_zero(self):
        principal = 10_000_000
        rate = 11.5
        months = 12
        emi = finance.loan_emi_paise(principal, rate, months)
        outstanding = principal
        for _ in range(months):
            _interest, _principal, _pay, outstanding = finance.emi_split(outstanding, rate, emi)
        assert outstanding == 0

    def test_final_payment_is_trued_up_not_overpaid(self):
        # A small remaining balance should be closed exactly by the "final"
        # payment logic rather than debiting a full EMI.
        outstanding = 500       # Rs 5 left
        rate = 11.5
        emi = 50_000            # a full EMI, far larger than what's owed
        interest, principal, pay, new_outstanding = finance.emi_split(outstanding, rate, emi)
        assert new_outstanding == 0
        assert principal == outstanding
        assert pay == interest + principal
        assert pay < emi


# --------------------------------------------------------------------------- #
# loan_totals
# --------------------------------------------------------------------------- #
class TestLoanTotals:
    def test_totals_are_consistent_with_the_schedule(self):
        principal = 10_000_000
        rate = 11.5
        months = 12
        emi, total_payable, total_interest = finance.loan_totals(principal, rate, months)
        schedule = finance.amortization_schedule(principal, rate, months, emi)

        assert emi == finance.loan_emi_paise(principal, rate, months)
        assert total_payable == sum(row["emi_paise"] for row in schedule)
        assert total_interest == total_payable - principal
        assert total_interest == sum(row["interest_paise"] for row in schedule)


# --------------------------------------------------------------------------- #
# add_months
# --------------------------------------------------------------------------- #
class TestAddMonths:
    def test_jan31_plus_1_month_clamps_to_feb28_in_common_year(self):
        assert finance.add_months(date(2023, 1, 31), 1) == date(2023, 2, 28)

    def test_jan31_plus_1_month_clamps_to_feb29_in_leap_year(self):
        assert finance.add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)

    def test_plus_60_months_advances_five_full_years(self):
        assert finance.add_months(date(2020, 7, 8), 60) == date(2025, 7, 8)

    def test_accepts_iso_date_string_input(self):
        assert finance.add_months("2024-01-31", 1) == date(2024, 2, 29)

    def test_crosses_year_boundary(self):
        assert finance.add_months(date(2024, 11, 30), 3) == date(2025, 2, 28)

    def test_zero_months_is_a_no_op(self):
        assert finance.add_months(date(2025, 3, 15), 0) == date(2025, 3, 15)
