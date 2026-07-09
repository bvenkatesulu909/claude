# API Examples — Bharath Bank of India

This guide demonstrates real-world usage patterns with curl and Python scripts. The base URL is `http://127.0.0.1:5055` (adjust for your deployment).

## 1. Authentication Flow

### Register a New Account

#### curl
```bash
curl -X POST http://127.0.0.1:5055/register \
  -d "full_name=Ramesh Patel" \
  -d "email=ramesh@example.com" \
  -d "phone=9876543210" \
  -d "password=SecurePass123" \
  -d "confirm=SecurePass123" \
  -d "account_type=Savings" \
  -d "opening_balance=50000" \
  -c cookies.txt
```

**Status:** 302 Found (redirects to `/dashboard`)  
**Headers:** Sets session cookie in `Set-Cookie`  
**Flash message:** "Welcome to Bharath Bank of India! Your account number is 172934815029."

#### Python
```python
import requests

session = requests.Session()
response = session.post(
    "http://127.0.0.1:5055/register",
    data={
        "full_name": "Ramesh Patel",
        "email": "ramesh@example.com",
        "phone": "9876543210",
        "password": "SecurePass123",
        "confirm": "SecurePass123",
        "account_type": "Savings",
        "opening_balance": "50000",
    },
)
print(f"Status: {response.status_code}")
# Response 302 with session cookie auto-managed by session object
# Next requests will include this cookie
```

---

### Login

#### curl
```bash
curl -X POST http://127.0.0.1:5055/login \
  -d "email=ramesh@example.com" \
  -d "password=SecurePass123" \
  -c cookies.txt
```

**Status:** 302 Found (redirects to `/dashboard`)  
**Flash message:** "Welcome back, Ramesh!"  
**Note:** Cookie is saved to `cookies.txt` and used in subsequent requests with `-b cookies.txt`.

#### Python
```python
import requests

session = requests.Session()
response = session.post(
    "http://127.0.0.1:5055/login",
    data={
        "email": "ramesh@example.com",
        "password": "SecurePass123",
    },
)
print(f"Status: {response.status_code}")
# Session automatically maintains the login cookie
```

---

### Logout

#### curl
```bash
curl -X GET http://127.0.0.1:5055/logout \
  -b cookies.txt
```

**Status:** 302 Found (redirects to `/`)  
**Flash message:** "You have been logged out securely."

---

## 2. Account Operations

### Get Dashboard (Account Summary)

#### curl
```bash
curl -X GET http://127.0.0.1:5055/dashboard \
  -b cookies.txt
```

**Status:** 200 OK  
**Response:** HTML page containing:
- Account number (e.g., "172934815029")
- Account type (e.g., "Savings")
- Current balance (displayed as "₹50,000.00")
- Last 5 transactions
- Portfolio summary (active deposits, investments, loans)
- KYC status

**Parsing the balance from HTML (example with BeautifulSoup):**
```python
from bs4 import BeautifulSoup

html = requests.get("http://127.0.0.1:5055/dashboard", cookies=session.cookies).text
soup = BeautifulSoup(html, "html.parser")
balance_text = soup.find("span", {"class": "balance"}).text
# Extract numeric value
balance = float(balance_text.replace("₹", "").replace(",", ""))
```

---

### Deposit Cash

#### curl
```bash
curl -X POST http://127.0.0.1:5055/deposit \
  -b cookies.txt \
  -d "amount=5000"
```

**Status:** 302 Found (redirects to `/dashboard`)  
**Flash message:** "₹5,000.00 deposited successfully."  
**Body:** Empty (HTML response body on redirect)

#### Python
```python
response = session.post(
    "http://127.0.0.1:5055/deposit",
    data={"amount": "5000"},
)
print(f"Status: {response.status_code}")
# Followed automatically if session.post(..., allow_redirects=True) [default]
```

**Error: Invalid amount**
```bash
curl -X POST http://127.0.0.1:5055/deposit \
  -b cookies.txt \
  -d "amount=-100"
```
**Status:** 302 Found (redirects back to `/deposit`)  
**Flash message:** "Amount must be greater than 0."

---

### Withdraw Cash

#### curl
```bash
curl -X POST http://127.0.0.1:5055/withdraw \
  -b cookies.txt \
  -d "amount=2000" \
  -d "description=ATM withdrawal"
```

**Status:** 302 Found (redirects to `/dashboard`)  
**Flash message:** "₹2,000.00 withdrawn successfully."

#### Python
```python
response = session.post(
    "http://127.0.0.1:5055/withdraw",
    data={
        "amount": "2000",
        "description": "ATM withdrawal",
    },
)
print(f"Status: {response.status_code}")
```

**Error: Insufficient balance**
```bash
# Try to withdraw ₹100,000 when balance is only ₹50,000
curl -X POST http://127.0.0.1:5055/withdraw \
  -b cookies.txt \
  -d "amount=100000"
```
**Status:** 302 Found (redirects to `/withdraw`)  
**Flash message:** "Insufficient balance for this withdrawal."

---

### Transfer Funds to Another Account

#### curl
```bash
curl -X POST http://127.0.0.1:5055/transfer \
  -b cookies.txt \
  -d "to_account=172934815030" \
  -d "amount=10000" \
  -d "description=Payment for goods"
```

**Status:** 302 Found (redirects to `/dashboard`)  
**Flash message:** "₹10,000.00 transferred to [Payee Name] (Ref TXN20240708001234)."  
**Note:** `to_account` is the payee's 12-digit account number.

#### Python
```python
response = session.post(
    "http://127.0.0.1:5055/transfer",
    data={
        "to_account": "172934815030",
        "amount": "10000",
        "description": "Payment for goods",
    },
)
print(f"Status: {response.status_code}")
```

**Error: Payee not found**
```bash
curl -X POST http://127.0.0.1:5055/transfer \
  -b cookies.txt \
  -d "to_account=999999999999" \
  -d "amount=5000"
```
**Status:** 302 Found  
**Flash message:** "Payee account number not found in Bharath Bank of India."

**Error: Transfer to own account**
```bash
# Same sender and receiver
curl -X POST http://127.0.0.1:5055/transfer \
  -b cookies.txt \
  -d "to_account=172934815029" \
  -d "amount=5000"
```
**Status:** 302 Found  
**Flash message:** "You cannot transfer money to your own account."

**Error: Insufficient balance**
```bash
curl -X POST http://127.0.0.1:5055/transfer \
  -b cookies.txt \
  -d "to_account=172934815030" \
  -d "amount=500000"
```
**Status:** 302 Found  
**Flash message:** "Insufficient balance for this transfer."

---

### Get Transaction Statement

#### curl
```bash
# All transactions
curl -X GET "http://127.0.0.1:5055/transactions" \
  -b cookies.txt

# Filter by CREDIT only
curl -X GET "http://127.0.0.1:5055/transactions?type=CREDIT" \
  -b cookies.txt

# Filter by DEBIT only
curl -X GET "http://127.0.0.1:5055/transactions?type=DEBIT" \
  -b cookies.txt
```

**Status:** 200 OK  
**Response:** HTML table containing:
- Date/Time of transaction
- Transaction type (CREDIT / DEBIT)
- Amount (in rupees)
- Running balance after each transaction
- Category (DEPOSIT, WITHDRAWAL, TRANSFER, FD, RD, LOAN)
- Description
- Reference number (TXN or REF prefix)

---

## 3. Deposits (Fixed & Recurring)

### List All Deposits

#### curl
```bash
curl -X GET http://127.0.0.1:5055/deposits \
  -b cookies.txt
```

**Status:** 200 OK  
**Response:** HTML page with:
- Table of all FD/RD deposits for this user
- Status (ACTIVE / MATURED / CLOSED)
- Scheme name and interest rate
- Principal, maturity amount, tenure
- Start and maturity dates
- Buttons to pay installment (RD) or close deposit

---

### Open a Fixed Deposit (FD)

#### curl
```bash
curl -X POST http://127.0.0.1:5055/deposits/open \
  -b cookies.txt \
  -d "scheme_code=FD_12M" \
  -d "amount=100000" \
  -d "tenure_months=12"
```

**Status:** 302 Found (redirects to `/deposits`)  
**Flash message:** "Classic FD 12 Month opened. Projected maturity ₹104,881.69 on 2025-07-09."  
**Note:** Amount is debited from savings account; maturity amount is calculated and stored.

#### Python
```python
response = session.post(
    "http://127.0.0.1:5055/deposits/open",
    data={
        "scheme_code": "FD_12M",
        "amount": "100000",
        "tenure_months": "12",
    },
)
print(f"Status: {response.status_code}")
```

**Error: Insufficient balance**
```bash
# Try to open FD with ₹500,000 when balance is only ₹50,000
curl -X POST http://127.0.0.1:5055/deposits/open \
  -b cookies.txt \
  -d "scheme_code=FD_12M" \
  -d "amount=500000" \
  -d "tenure_months=12"
```
**Status:** 302 Found  
**Flash message:** "Insufficient balance in your savings account."

**Error: Tenure out of range**
```bash
curl -X POST http://127.0.0.1:5055/deposits/open \
  -b cookies.txt \
  -d "scheme_code=FD_12M" \
  -d "amount=50000" \
  -d "tenure_months=36"  # Max 12 months
```
**Status:** 302 Found  
**Flash message:** "Tenure for Classic FD 12 Month must be 12–12 months."

**Error: Amount below minimum**
```bash
curl -X POST http://127.0.0.1:5055/deposits/open \
  -b cookies.txt \
  -d "scheme_code=FD_12M" \
  -d "amount=100" \
  -d "tenure_months=12"
```
**Status:** 302 Found  
**Flash message:** "Minimum for Classic FD 12 Month is ₹10,000.00."

---

### Open a Recurring Deposit (RD)

#### curl
```bash
curl -X POST http://127.0.0.1:5055/deposits/open \
  -b cookies.txt \
  -d "scheme_code=RD_60M" \
  -d "amount=5000" \
  -d "tenure_months=60"
```

**Status:** 302 Found (redirects to `/deposits`)  
**Flash message:** "Recurring Deposit 60 Months opened. Projected maturity ₹324,456.78 on 2030-07-09."  
**Note:** First ₹5,000 is debited immediately; remaining installments are collected monthly. `installments_paid` starts at 1.

#### Python
```python
response = session.post(
    "http://127.0.0.1:5055/deposits/open",
    data={
        "scheme_code": "RD_60M",
        "amount": "5000",
        "tenure_months": "60",
    },
)
```

**Error: Amount below monthly minimum**
```bash
curl -X POST http://127.0.0.1:5055/deposits/open \
  -b cookies.txt \
  -d "scheme_code=RD_60M" \
  -d "amount=500" \
  -d "tenure_months=60"
```
**Status:** 302 Found  
**Flash message:** "Minimum for Recurring Deposit 60 Months is ₹1,000.00 per month."

---

### Pay RD Installment

#### curl
```bash
# For deposit ID 5 (RD)
curl -X POST http://127.0.0.1:5055/deposits/5/pay \
  -b cookies.txt
```

**Status:** 302 Found (redirects to `/deposits`)  
**Flash message:** "Recurring Deposit 60 Months installment paid. (Installment 2 of 60)"

#### Python
```python
response = session.post(
    "http://127.0.0.1:5055/deposits/5/pay",
)
print(f"Status: {response.status_code}")
```

**Error: Deposit not found / not an RD / not active**
```bash
curl -X POST http://127.0.0.1:5055/deposits/99/pay \
  -b cookies.txt
```
**Status:** 302 Found  
**Flash message:** "Recurring deposit not found."

**Error: All installments paid**
```bash
# If RD is fully paid (installments_paid == tenure_months)
curl -X POST http://127.0.0.1:5055/deposits/5/pay \
  -b cookies.txt
```
**Status:** 302 Found  
**Flash message:** "All installments for this RD have already been paid."

**Error: Insufficient balance**
```bash
curl -X POST http://127.0.0.1:5055/deposits/5/pay \
  -b cookies.txt
```
**Status:** 302 Found (when savings balance < monthly installment)  
**Flash message:** "Insufficient balance for this installment."

---

### Close a Deposit

#### curl
```bash
# For deposit ID 3
curl -X POST http://127.0.0.1:5055/deposits/3/close \
  -b cookies.txt
```

**Status:** 302 Found (redirects to `/deposits`)

**If maturity date reached:**
**Flash message:** "Fixed Deposit closed and maturity amount ₹104,881.69 credited to your account."

**If maturity date not reached (early close):**
**Flash message:** "Fixed Deposit closed. Principal ₹100,000.00 credited to your account (no interest on early closure)."

#### Python
```python
response = session.post(
    "http://127.0.0.1:5055/deposits/3/close",
)
print(f"Status: {response.status_code}")
```

---

## 4. Loans

### List Available Loan Products

#### curl
```bash
# This is public (no auth required), but shows on authenticated /loans page
curl -X GET http://127.0.0.1:5055/products \
  -b cookies.txt
```

**Status:** 200 OK  
**Response:** HTML listing all loan products with:
- Product name
- Interest rate (%, per annum)
- Min/Max loan amount
- Max tenure (months)
- Processing fee (%)
- Description

---

### Apply for a Loan

#### curl
```bash
curl -X POST http://127.0.0.1:5055/loans/apply \
  -b cookies.txt \
  -d "product_code=PL001" \
  -d "amount=200000" \
  -d "tenure_months=24" \
  -d "purpose=Home renovation"
```

**Status:** 302 Found (redirects to `/loans/<loan_id>` on approval, or `/loans` on rejection)  

**On approval:**
**Flash message:** "Congratulations! Your Personal Loan of ₹2,00,000.00 is approved and disbursed to your savings account. EMI ₹8,834.50/month."

**On rejection:**
**Flash message:** "Your Personal Loan application could not be approved. The EMI would exceed 55% of your monthly income (FOIR limit). Try a smaller amount or a longer tenure."

#### Python
```python
response = session.post(
    "http://127.0.0.1:5055/loans/apply",
    data={
        "product_code": "PL001",
        "amount": "200000",
        "tenure_months": "24",
        "purpose": "Home renovation",
    },
)
print(f"Status: {response.status_code}")
# Loan is instantly ACTIVE or REJECTED; decision is stored in decision_reason
```

**Error: KYC not completed**
```bash
curl -X POST http://127.0.0.1:5055/loans/apply \
  -b cookies.txt \
  -d "product_code=PL001" \
  -d "amount=200000" \
  -d "tenure_months=24"
```
**Status:** 302 Found (redirects to `/kyc`)  
**Flash message:** "Please complete your KYC (including annual income) before applying for a loan."

**Error: Invalid product**
```bash
curl -X POST http://127.0.0.1:5055/loans/apply \
  -b cookies.txt \
  -d "product_code=INVALID_CODE" \
  -d "amount=200000" \
  -d "tenure_months=24"
```
**Status:** 302 Found  
**Flash message:** "Please choose a valid loan product."

**Error: Amount out of range**
```bash
curl -X POST http://127.0.0.1:5055/loans/apply \
  -b cookies.txt \
  -d "product_code=PL001" \
  -d "amount=50000000" \
  -d "tenure_months=24"
```
**Status:** 302 Found  
**Flash message:** "Your Personal Loan application could not be approved. Amount must be between ₹50,000.00 and ₹5,000,000.00."

**Error: Tenure out of range**
```bash
curl -X POST http://127.0.0.1:5055/loans/apply \
  -b cookies.txt \
  -d "product_code=PL001" \
  -d "amount=200000" \
  -d "tenure_months=120"
```
**Status:** 302 Found  
**Flash message:** "Your Personal Loan application could not be approved. Tenure must be between 6 and 60 months."

**Error: FOIR (Finance-to-Income Ratio) check fails**
```bash
# EMI > 55% of monthly income
curl -X POST http://127.0.0.1:5055/loans/apply \
  -b cookies.txt \
  -d "product_code=PL001" \
  -d "amount=5000000" \
  -d "tenure_months=24"
```
**Status:** 302 Found  
**Flash message:** "Your Personal Loan application could not be approved. The EMI would exceed 55% of your monthly income (FOIR limit). Try a smaller amount or a longer tenure."

---

### Get Loan Detail & Amortization Schedule

#### curl
```bash
# For loan ID 2
curl -X GET http://127.0.0.1:5055/loans/2 \
  -b cookies.txt
```

**Status:** 200 OK  
**Response:** HTML page containing:
- Loan account number (e.g., "BBILN20240708001")
- Product name and interest rate
- Principal, EMI, tenure, total payable
- Status (ACTIVE / CLOSED / REJECTED)
- If approved: Full amortization schedule (month, EMI, principal, interest, outstanding balance)
- If approved: Payment history (actual EMI payments made)
- Decision reason (if rejected)

#### Python
```python
html = requests.get(
    "http://127.0.0.1:5055/loans/2",
    cookies=session.cookies
).text
soup = BeautifulSoup(html, "html.parser")
# Parse amortization table, loan details, etc.
```

**Error: Loan not found or doesn't belong to user**
```bash
curl -X GET http://127.0.0.1:5055/loans/9999 \
  -b cookies.txt
```
**Status:** 404 Not Found

---

### Pay Loan EMI

#### curl
```bash
# Pay next EMI for loan ID 2
curl -X POST http://127.0.0.1:5055/loans/2/pay \
  -b cookies.txt
```

**Status:** 302 Found (redirects to `/loans/<loan_id>`)  
**Flash message:** "EMI ₹8,834.50 paid successfully. (EMI 1 of 24)"

#### Python
```python
response = session.post(
    "http://127.0.0.1:5055/loans/2/pay",
)
print(f"Status: {response.status_code}")
# Outstanding balance is reduced; status flips to CLOSED when outstanding reaches 0
```

**Error: Loan not found / not active**
```bash
curl -X POST http://127.0.0.1:5055/loans/9999/pay \
  -b cookies.txt
```
**Status:** 302 Found (redirects to `/loans`)  
**Flash message:** "Loan not found or not active."

**Error: Insufficient balance**
```bash
curl -X POST http://127.0.0.1:5055/loans/2/pay \
  -b cookies.txt
```
**Status:** 302 Found (when savings balance < EMI amount)  
**Flash message:** "Insufficient balance to pay this EMI. Current balance ₹5,000.00, EMI ₹8,834.50."

---

## 5. JSON API

### Get Account Balance (JSON)

#### curl
```bash
curl -X GET http://127.0.0.1:5055/api/balance \
  -b cookies.txt
```

**Status:** 200 OK  
**Content-Type:** `application/json`

**Response:**
```json
{
  "account_number": "172934815029",
  "ifsc": "BBIN0001729",
  "balance": 15250.75,
  "currency": "INR"
}
```

#### Python
```python
response = session.get("http://127.0.0.1:5055/api/balance")
data = response.json()
print(f"Account: {data['account_number']}")
print(f"Balance: ₹{data['balance']}")
print(f"IFSC: {data['ifsc']}")
```

**Error: Not authenticated**
```bash
curl -X GET http://127.0.0.1:5055/api/balance
# (without -b cookies.txt)
```
**Status:** 302 Found (redirects to `/login`)

---

## 6. KYC (Account Holder Information)

### Submit KYC Information

#### curl
```bash
curl -X POST http://127.0.0.1:5055/kyc \
  -b cookies.txt \
  -d "dob=1985-06-15" \
  -d "gender=M" \
  -d "address=123 Main Street" \
  -d "city=Hyderabad" \
  -d "state=Telangana" \
  -d "pincode=500032" \
  -d "pan=ABCDE1234F" \
  -d "aadhaar_last4=1234" \
  -d "occupation=Software Engineer" \
  -d "annual_income=1200000" \
  -d "nominee_name=Priya Patel" \
  -d "nominee_relation=Spouse"
```

**Status:** 302 Found (redirects to `/kyc`)  
**Flash message:** "KYC information updated. Status: VERIFIED."  
**Note:** KYC status becomes VERIFIED once DOB, address, PAN, Aadhaar-last-4, and annual income are all present.

#### Python
```python
response = session.post(
    "http://127.0.0.1:5055/kyc",
    data={
        "dob": "1985-06-15",
        "gender": "M",
        "address": "123 Main Street",
        "city": "Hyderabad",
        "state": "Telangana",
        "pincode": "500032",
        "pan": "ABCDE1234F",
        "aadhaar_last4": "1234",
        "occupation": "Software Engineer",
        "annual_income": "1200000",
        "nominee_name": "Priya Patel",
        "nominee_relation": "Spouse",
    },
)
print(f"Status: {response.status_code}")
```

**Error: Invalid annual income**
```bash
curl -X POST http://127.0.0.1:5055/kyc \
  -b cookies.txt \
  -d "annual_income=invalid"
```
**Status:** 302 Found  
**Flash message:** "Please enter a valid annual income."

---

## 7. Common Error Scenarios

### Invalid Form Data

**Scenario:** Missing or invalid field (e.g., empty amount, non-numeric)

```bash
curl -X POST http://127.0.0.1:5055/deposit \
  -b cookies.txt \
  -d "amount=abc"
```

**Status:** 302 Found (redirects back to form page)  
**Flash message:** "Amount must be greater than 0." or "Enter a valid amount..."

---

### Insufficient Balance

**Scenario:** Attempting any debit operation (withdraw, transfer, deposit opening, RD installment, EMI payment) with insufficient funds.

```bash
curl -X POST http://127.0.0.1:5055/withdraw \
  -b cookies.txt \
  -d "amount=999999"
```

**Status:** 302 Found  
**Flash message:** "Insufficient balance for this [operation]."

---

### Session Expired / Not Authenticated

**Scenario:** Attempting to access authenticated route without valid session.

```bash
curl -X GET http://127.0.0.1:5055/dashboard
# No cookie provided
```

**Status:** 302 Found (redirects to `/login`)  
**Flash message:** "Please log in first."

---

### Resource Not Found

**Scenario:** Attempting to access a resource (loan, deposit) that doesn't exist or doesn't belong to the user.

```bash
curl -X GET http://127.0.0.1:5055/loans/9999 \
  -b cookies.txt
```

**Status:** 404 Not Found

---

## Testing with Python Requests

### Complete End-to-End Workflow

```python
import requests
import json
from bs4 import BeautifulSoup

# Initialize session (maintains cookies)
session = requests.Session()
BASE_URL = "http://127.0.0.1:5055"

# Step 1: Register
print("1. Registering new user...")
reg_response = session.post(
    f"{BASE_URL}/register",
    data={
        "full_name": "Amit Kumar",
        "email": "amit@example.com",
        "phone": "9999999999",
        "password": "Password123",
        "confirm": "Password123",
        "account_type": "Savings",
        "opening_balance": "500000",
    },
)
print(f"   Status: {reg_response.status_code}")

# Step 2: Check balance
print("2. Getting account balance (JSON API)...")
balance_response = session.get(f"{BASE_URL}/api/balance")
balance_data = balance_response.json()
print(f"   Account: {balance_data['account_number']}")
print(f"   Balance: ₹{balance_data['balance']}")

# Step 3: Deposit cash
print("3. Depositing cash...")
deposit_response = session.post(
    f"{BASE_URL}/deposit",
    data={"amount": "50000"},
)
print(f"   Status: {deposit_response.status_code}")

# Step 4: Update KYC for loan eligibility
print("4. Updating KYC...")
kyc_response = session.post(
    f"{BASE_URL}/kyc",
    data={
        "dob": "1990-01-01",
        "gender": "M",
        "address": "123 Street",
        "city": "Bangalore",
        "state": "Karnataka",
        "pincode": "560001",
        "pan": "AAAAA0000A",
        "aadhaar_last4": "1234",
        "occupation": "Engineer",
        "annual_income": "2000000",
        "nominee_name": "Jane Doe",
        "nominee_relation": "Spouse",
    },
)
print(f"   Status: {kyc_response.status_code}")

# Step 5: Apply for loan
print("5. Applying for Personal Loan...")
loan_response = session.post(
    f"{BASE_URL}/loans/apply",
    data={
        "product_code": "PL001",
        "amount": "200000",
        "tenure_months": "24",
        "purpose": "Home renovation",
    },
)
print(f"   Status: {loan_response.status_code}")

# Step 6: Check updated balance
print("6. Checking balance after loan disbursement...")
balance_response = session.get(f"{BASE_URL}/api/balance")
balance_data = balance_response.json()
print(f"   Balance: ₹{balance_data['balance']}")

# Step 7: Open a Fixed Deposit
print("7. Opening Fixed Deposit...")
fd_response = session.post(
    f"{BASE_URL}/deposits/open",
    data={
        "scheme_code": "FD_12M",
        "amount": "100000",
        "tenure_months": "12",
    },
)
print(f"   Status: {fd_response.status_code}")

print("\nWorkflow complete!")
```

---

## Notes on Session Management

- **Cookies:** All authenticated requests require a valid session cookie. Use `-c` to save cookies in curl, `-b` to send them in subsequent requests.
- **Redirects:** The application uses 302 redirects for POST operations. Follow these redirects with `curl -L` or `requests.Session` (which auto-follows).
- **Flash Messages:** Success/error messages are stored in session flash. Parse the HTML to extract messages or look for CSS classes like `.alert-success`, `.alert-danger`.
- **JSON Responses:** Only `/api/balance` returns JSON; all other routes return HTML.

---

## Field Formats

| Field | Format | Example |
|---|---|---|
| Account Number | 12 digits (branch code + 8 random) | `172934815029` |
| IFSC Code | Fixed for demo bank | `BBIN0001729` |
| Amount | Decimal rupees (₹) | `50000` or `10000.50` |
| Date of Birth | ISO date (YYYY-MM-DD) | `1985-06-15` |
| PAN | 10 uppercase alphanumeric | `ABCDE1234F` |
| Tenure | Integer months | `12`, `24`, `60` |
| Loan Account | `BBILN` + 8 digits | `BBILN20240708001` |
| Reference No | `TXN` or `REF` + timestamp | `TXN20240708123456` |

---

## Deployment Considerations

- Change `http://127.0.0.1:5055` to your live domain/port.
- Update `SECRET_KEY` environment variable on production.
- Use HTTPS in production; cookies should have `Secure` and `HttpOnly` flags.
- Consider adding rate limiting to prevent brute-force login/registration attacks.
