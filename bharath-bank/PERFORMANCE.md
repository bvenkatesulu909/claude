# Database Performance Analysis: Bharath Bank App

## Executive Summary

Analysis of `app.py` reveals **0 explicit database indexes** beyond PRIMARY KEY constraints. The schema has 8 tables with numerous foreign keys and frequent queries on non-indexed columns. While no classic N+1 query patterns were detected, **7 critical indexes are missing** that will cause significant slowdowns at scale (~100k+ rows).

---

## Current Index Status

### Tables and Their Primary Keys (Auto-Indexed)

| Table | Primary Key | Status |
|-------|-------------|--------|
| `users` | `id` | ✓ Indexed (PK) |
| `accounts` | `id` | ✓ Indexed (PK) |
| `transactions` | `id` | ✓ Indexed (PK) |
| `customer_profiles` | `user_id` | ✓ Indexed (PK) |
| `schemes` | `code` | ✓ Indexed (PK) |
| `loan_products` | `code` | ✓ Indexed (PK) |
| `deposits` | `id` | ✓ Indexed (PK) |
| `loans` | `id` | ✓ Indexed (PK) |
| `loan_payments` | `id` | ✓ Indexed (PK) |

**Explicit Secondary Indexes:** None found in `init_db()` or any other module.

---

## Query Analysis by Route

### 1. High-Frequency Queries Without Indexes

#### **transactions(account_id) — Multiple Locations** 
- **Lines:** 525-528 (dashboard), 633-634 (transactions page), 1055 (statement_rows)
- **Query:** `SELECT * FROM transactions WHERE account_id = ? [AND created_at >= ?] [AND created_at <= ?] ORDER BY id ASC`
- **Issue:** No index on `(account_id, created_at)`. Full table scan of entire transactions table.
- **Impact:** ⚠️ Critical at 100k+ rows. Dashboard fetches last 5 txns = O(n) without index.

#### **accounts(user_id) — get_primary_account()**
- **Lines:** 357-359 (called ~30+ times across routes)
- **Query:** `SELECT * FROM accounts WHERE user_id = ? ORDER BY id LIMIT 1`
- **Issue:** No index on `user_id`. Full table scan of accounts.
- **Impact:** ⚠️ Medium. Accounts table smaller, but called on almost every authenticated page.

#### **deposits(user_id) — deposits_for()**
- **Lines:** 368-375 (called in deposits_page, portfolio_summary)
- **Query:** `SELECT * FROM deposits WHERE user_id = ? [AND status = ?] ORDER BY id DESC`
- **Issue:** No index on `(user_id, status)`. Filters by status in SQL (good), but no index.
- **Impact:** ⚠️ Medium. Grows with customer deposits (typically <100 per customer).

#### **loans(user_id) — loans_for()**
- **Lines:** 378-385 (called in loans_page, portfolio_summary)
- **Query:** `SELECT * FROM loans WHERE user_id = ? [AND status = ?] ORDER BY id DESC`
- **Issue:** No index on `(user_id, status)`. Filters by status in SQL (good), but no index.
- **Impact:** ⚠️ Medium. Grows with customer loans (typically <50 per customer).

#### **accounts(account_number) — transfer() lookup**
- **Lines:** 590-593 (JOIN on account_number)
- **Query:** `SELECT a.*, u.full_name FROM accounts a JOIN users u ON u.id = a.user_id WHERE a.account_number = ?`
- **Issue:** No index on `account_number`. Full table scan for every transfer.
- **Impact:** ⚠️ High. Executed on every transfer, join with users.

#### **loans(loan_account) — apply_loan() & gen_loan_account()**
- **Lines:** 412, 960-961 (after insert, lookup by loan_account)
- **Query:** `SELECT 1 FROM loans WHERE loan_account = ?`
- **Issue:** No index on `loan_account`. Full table scan to verify uniqueness and retrieve.
- **Impact:** ⚠️ Medium. Called during loan application.

#### **loan_payments(loan_id) — loan_detail()**
- **Lines:** 984-985 (fetch all EMI payments for a loan)
- **Query:** `SELECT * FROM loan_payments WHERE loan_id = ? ORDER BY emi_no`
- **Issue:** No index on `loan_id`. Full table scan of loan_payments table.
- **Impact:** ⚠️ Medium. User views loan detail page; scales with payment count (~60 EMIs typical).

---

## N+1 Query Audit

### Findings: ✅ No Classic N+1 Patterns Detected

The code avoids the standard "loop through rows, query each" antipattern:

- ✅ **portfolio_summary()** (lines 388-406): Two aggregate queries, not per-item queries
- ✅ **dashboard()** (lines 519-532): Single transaction fetch, not loop+query per user
- ✅ **loans_page()** (lines 868-876): Single `loans_for()` call, not loop
- ✅ **statement_rows()** (statement_export.py, lines 102-138): Single ordered query with filters, not per-transaction lookups
- ✅ **loan_detail()** (lines 970-987): One loan + one payments fetch, not loop

**However:** Query efficiency is still poor due to missing indexes (see above).

---

## Unnecessary Full-Table Scans

### Acceptably Scanned (Small Reference Tables)

- **products()** (lines 707-715): `SELECT * FROM schemes`, `SELECT * FROM loan_products`
  - ✓ Fine: Reference data (~8-12 rows), scanned rarely
  - Cache or front-end loading recommended long-term

### Potential Optimization (Statement Queries)

- **statement_rows()** (lines 113-124): Queries transactions with filters on `(account_id, created_at)`
  - Without index: Full scan of entire transactions table
  - Better: Use composite index to avoid scan

---

## Load-Test Projections (~100k Rows)

### Scenario: 10,000 customers × ~10 transactions each = 100k transactions

| Query | Current (No Index) | With Recommended Index | Speedup |
|-------|-------------------|----------------------|---------|
| Dashboard (last 5 txns for 1 account) | ~10-50ms (scan all 100k) | <1ms (seek + limit) | **10-50x** |
| Statement export (date range filter) | ~50-200ms (scan all 100k) | <5ms (range scan) | **10-40x** |
| Transfer lookup by account number | ~5-20ms (scan 10k accounts) | <1ms (seek) | **5-20x** |
| List customer deposits | ~1-5ms (scan 100k deposits) | <1ms (seek) | **1-5x** |
| Admin dashboard aggregate (SUM balance) | ~20-50ms (scan all accounts) | ~20-50ms (no change; aggregate) | **0x** |

---

## Recommended Optimizations

### Priority 1: Critical (Add Immediately)

#### 1. **Index on transactions(account_id, created_at)**
```sql
CREATE INDEX idx_transactions_account_created 
ON transactions(account_id, created_at);
```
- **Why:** Dashboard, statement export, transaction list queries depend on this.
- **Benefit:** 10-50x speedup on transaction queries.
- **Lines affected:** 525-528, 633-634, 1055 (statement_rows).

#### 2. **Index on accounts(user_id)**
```sql
CREATE INDEX idx_accounts_user_id 
ON accounts(user_id);
```
- **Why:** get_primary_account() called ~30+ times per authenticated request.
- **Benefit:** 5-10x speedup on account lookups.
- **Lines affected:** 357-359 (called from ~30 routes).

#### 3. **Index on accounts(account_number)**
```sql
CREATE INDEX idx_accounts_account_number 
ON accounts(account_number);
```
- **Why:** Transfer lookup and account number uniqueness checks.
- **Benefit:** 5-20x speedup on transfer operations.
- **Lines affected:** 590-593 (transfer), 312 (gen_account_number).

### Priority 2: Important (Add Within Sprint)

#### 4. **Composite Index on deposits(user_id, status)**
```sql
CREATE INDEX idx_deposits_user_status 
ON deposits(user_id, status);
```
- **Why:** deposits_for() filters by both user_id and status.
- **Benefit:** Avoid full table scan; can fetch status=ACTIVE deposits in O(log n).
- **Lines affected:** 368-375, 391-396 (portfolio_summary).

#### 5. **Composite Index on loans(user_id, status)**
```sql
CREATE INDEX idx_loans_user_status 
ON loans(user_id, status);
```
- **Why:** loans_for() filters by both user_id and status.
- **Benefit:** Avoid full table scan; can fetch status=ACTIVE loans in O(log n).
- **Lines affected:** 378-385, 397-399 (portfolio_summary).

#### 6. **Index on loan_payments(loan_id)**
```sql
CREATE INDEX idx_loan_payments_loan_id 
ON loan_payments(loan_id);
```
- **Why:** loan_detail() fetches all payments for a loan.
- **Benefit:** O(log n) seek instead of full table scan.
- **Lines affected:** 984-985 (loan_detail).

#### 7. **Index on loans(loan_account)**
```sql
CREATE INDEX idx_loans_loan_account 
ON loans(loan_account);
```
- **Why:** apply_loan() and gen_loan_account() query by loan_account.
- **Benefit:** O(log n) lookup instead of O(n).
- **Lines affected:** 412, 960-961 (apply_loan).

---

## Implementation Strategy

### Phase 1: Create Indexes (No Schema Changes)
```sql
-- Run these statements in sqlite3 CLI or via Python:
CREATE INDEX idx_transactions_account_created ON transactions(account_id, created_at);
CREATE INDEX idx_accounts_user_id ON accounts(user_id);
CREATE INDEX idx_accounts_account_number ON accounts(account_number);
CREATE INDEX idx_deposits_user_status ON deposits(user_id, status);
CREATE INDEX idx_loans_user_status ON loans(user_id, status);
CREATE INDEX idx_loan_payments_loan_id ON loan_payments(loan_id);
CREATE INDEX idx_loans_loan_account ON loans(loan_account);
```

### Phase 2: Verify with Load Test
1. Create ~100k rows using `seed_demo.py`
2. Benchmark statement export, dashboard, transfers with and without indexes
3. Confirm speedups match projections above

### Phase 3: Update init_db() (Optional but Recommended)
Add index creation to `init_db()` function in app.py (after CREATE TABLE statements) so new deployments include indexes:
```python
def init_db():
    db = sqlite3.connect(DB_FILE)
    db.executescript("""
        -- [existing CREATE TABLE statements] ...
        -- [at end, add:]
        CREATE INDEX IF NOT EXISTS idx_transactions_account_created 
            ON transactions(account_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_accounts_user_id 
            ON accounts(user_id);
        -- ... [etc.]
    """)
    db.commit()
```

---

## Code-Level Optimizations (Future)

### Request-Level Caching
Cache `get_primary_account(uid)` at request level to avoid repeated queries:
```python
def get_primary_account(user_id):
    cache_key = f"primary_account_{user_id}"
    if cache_key in g:
        return g[cache_key]
    account = get_db().execute(...).fetchone()
    g[cache_key] = account
    return account
```
- **Benefit:** Eliminate 5-10 duplicate queries per request
- **Impact:** 10-20% speedup on authenticated pages

### Defer Non-Critical Aggregates
Move `portfolio_summary()` aggregates to async task for heavy users:
```python
# Current: 2 aggregate queries on every dashboard load
summary = portfolio_summary(uid)

# Future: Cache result, update on deposit/loan changes
summary = get_cached_portfolio_summary(uid)  # <1ms
```

### Pagination for Large Statements
statement_export.py could paginate if statement periods exceed 10k rows:
```python
# Current: Fetches all transactions, renders all in memory
rows = statement_rows(db, account_id, start, end)

# Future: Paginate with LIMIT/OFFSET for very large statements
rows = statement_rows(db, account_id, start, end, limit=1000, offset=0)
```

---

## Summary

| Category | Count | Status |
|----------|-------|--------|
| **Explicit Indexes** | 0 | ❌ Missing |
| **N+1 Patterns** | 0 | ✅ None detected |
| **Recommended Indexes** | 7 | ⚠️ Critical for scale |
| **Potential Speedups** | 5-50x | For index queries at 100k rows |

**Action:** Add 7 indexes before deploying to production with significant transaction volume. The dashboard and statement queries will become unusable above ~10-20k transactions without them.

---

## Testing Checklist

- [ ] Run `sqlite3 bank.db ".indices"` to verify indexes after creation
- [ ] Benchmark dashboard load time before/after (aim for <100ms response)
- [ ] Benchmark statement export with 1000+ transaction rows
- [ ] Benchmark transfer lookup by account number
- [ ] Run `EXPLAIN QUERY PLAN` on critical queries to confirm index usage:
  ```sql
  EXPLAIN QUERY PLAN SELECT * FROM transactions WHERE account_id = ? 
    AND created_at >= ? ORDER BY id ASC LIMIT 5;
  ```
  Should show "SEARCH transactions USING idx_transactions_account_created"
- [ ] Load test with 100k rows; confirm no queries exceed 50ms

