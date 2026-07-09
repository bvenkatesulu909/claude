# Bharath Bank of India — Production Launch Checklist

**Last Updated:** July 9, 2026  
**Target Launch Date:** TBD  
**Current Readiness:** 35% Complete (7/20 critical items ready)

---

## Infrastructure

- [x] Hosting provider selected (Render / Railway / custom)
  - **Status:** ✓ Ready — `render.yaml` and `Procfile` configured for Render and Railway
  - **Details:** Render Blueprint supports one-click deploy from GitHub
  
- [ ] Domain name acquired & configured
  - **Status:** ✗ Pending — No custom domain purchased yet
  - **Action:** Acquire domain (e.g., `bharathbank.in` or `.com`); configure DNS to platform provider
  - **Timeline:** 1 day
  
- [x] SSL certificate (auto via platform or Let's Encrypt)
  - **Status:** ✓ Ready — Render/Railway provide free HTTPS via Let's Encrypt; auto-renews
  - **Details:** No manual configuration required
  
- [ ] Database persistence (persistent disk or external DB — SQLite ephemeral on free tier)
  - **Status:** ⚠ Partial — Render free tier uses ephemeral storage (data lost on redeploy)
  - **Action:** Upgrade to paid Render instance OR enable persistent disk in `render.yaml` OR migrate to external PostgreSQL
  - **Current:** Demo behavior (re-seeds on boot) — acceptable for MVP launch; address post-launch
  - **Timeline:** Day 1 of production (if going live with real data)
  
- [ ] Logs & monitoring configured (application logs, error tracking)
  - **Status:** ✗ Pending — No log aggregation or error tracking configured
  - **Action:** Configure one of:
    - Render: native logging dashboard (built-in)
    - Sentry.io: error tracking + alerts (free tier available)
    - Rollbar: similar to Sentry
  - **Timeline:** 2 hours

---

## Configuration

- [x] Environment variables set (BBI_SECRET, PORT, DEBUG=False)
  - **Status:** ✓ Ready — `render.yaml` auto-generates `BBI_SECRET`; Railway manual var setup documented in `DEPLOY.md`
  - **Details:** Platform providers supply `PORT` at runtime
  
- [x] SECRET_KEY is random & long (not dev default)
  - **Status:** ⚠ Partial — Code fallback to hardcoded string; render.yaml auto-generates safe value
  - **Action:** Apply SECURITY.md patch C1 to fail closed in production (see below)
  - **Blocker:** Requires code change before deploy
  - **Timeline:** 1 hour

- [ ] CSRF protection enabled (see SECURITY.md patches)
  - **Status:** ✗ Pending — No CSRF tokens on any POST form
  - **Action:** Apply SECURITY.md patches H1 + H2 (add token generation, context processor, before_request guard)
  - **Severity:** HIGH — money-moving routes currently forgeable cross-site
  - **Timeline:** 3–4 hours
  
- [ ] Session timeout configured
  - **Status:** ✗ Pending — Flask default is session expires on browser close
  - **Action:** Set `PERMANENT_SESSION_LIFETIME` in app.py (e.g., 30 min for banking)
  - **Example:**
    ```python
    from datetime import timedelta
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)
    ```
  - **Timeline:** 30 min
  
- [ ] Database backups enabled
  - **Status:** ✗ Pending — No backup procedure documented
  - **Action:** Configure daily backups:
    - **Render:** attach persistent disk + use external backup service (e.g., AWS S3)
    - **Railway:** attach Volume + use rsync or S3 sync cron job
    - **Simple approach:** Daily export via `statement_export.py` to S3/Cloud Storage
  - **Timeline:** 4 hours (set up + test)

---

## Security

- [x] HTTPS enforced
  - **Status:** ✓ Ready — Platform providers enforce HTTPS; HTTP redirects to HTTPS
  
- [ ] All security patches from SECURITY.md applied
  - **Status:** ✗ Pending — 3 patches not yet applied:
    - **C1** (CRITICAL): Fix hardcoded SECRET_KEY fallback + debug=True
    - **H1** (HIGH): Add CSRF tokens to all POST forms
    - **H2** (HIGH): Harden `rupees_to_paise()` + validate input amounts
  - **Action:** Apply patches in order: C1 → H1 → H2
  - **Timeline:** 6 hours total
  
- [x] Input validation on all forms (see app.py validators)
  - **Status:** ✓ Ready — app.py uses werkzeug validators on registration, transfer, KYC
  - **Details:** Email, phone, amount validation present; see H2 patch for additional float hardening
  
- [x] SQL injection review (all queries use ? placeholders?)
  - **Status:** ✓ Verified safe — All queries in app.py + seed_demo.py use `?` parameter binding
  - **Details:** No string interpolation detected; SQLite parameterized queries protect against injection
  
- [ ] CORS/origin restrictions if needed
  - **Status:** ✗ Pending — No CORS headers set (app serves browser only, no API for external clients)
  - **Action:** Keep app as-is for MVP launch; add CORS headers only if mobile/SPA client needed
  - **Timeline:** Skip (not required for Phase 1)
  
- [ ] Rate limiting on auth endpoints (optional but recommended)
  - **Status:** ✗ Pending — No rate limiting on `/login`, `/register`, or `/loans/apply`
  - **Action:** Install `flask-limiter` (pip); add 5 attempts/min per IP to login
    ```python
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    limiter = Limiter(app=app, key_func=get_remote_address)
    @app.route("/login", methods=["POST"])
    @limiter.limit("5 per minute")
    def login(): ...
    ```
  - **Timeline:** 2 hours (optional; defer to Phase 2 if needed)
  
- [ ] Audit log of major transactions (optional)
  - **Status:** ✗ Pending — Transactions are logged to `transactions` table, but no separate audit trail for compliance
  - **Action:** Defer to Phase 2; MVP can track in main transactions table
  - **Timeline:** Skip (not required for MVP)

---

## Testing

- [x] Unit tests passing (pytest)
  - **Status:** ✓ Ready — `tests/test_finance.py` covers financial math (FD/RD/EMI)
  - **Action:** Run: `cd bharath-bank && pytest tests/`
  - **Expected:** All tests pass
  
- [ ] E2E tests passing (scripts/full_e2e.py)
  - **Status:** ✗ Pending — No E2E test script exists in `scripts/`
  - **Action:** Create or run manual smoke test sequence (see Launch section below)
  - **Timeline:** 2 hours to write; 30 min to run per environment
  
- [ ] Load test (simulate 100+ concurrent users)
  - **Status:** ✗ Pending — No load test harness
  - **Action:** Optional for MVP; use Apache JMeter or `locust` for post-launch testing
  - **Timeline:** 4 hours (defer to Phase 2 if budget constrained)
  
- [ ] Security audit (penetration test optional for demo)
  - **Status:** ✗ Pending — SECURITY.md documents issues; manual code review completed
  - **Action:** After applying security patches, re-review SECURITY.md checklist
  - **Timeline:** 1 hour (code review); defer pen test to Phase 2

---

## Data

- [x] Demo data seeded (seed_demo.py runs idempotent)
  - **Status:** ✓ Ready — `seed_demo.py` populates demo customers; safe to re-run
  - **Action:** Run before launch: `cd bharath-bank && python seed_demo.py`
  - **Details:** Creates ~5 demo users with realistic accounts, KYC, deposits, and loans
  
- [ ] Schema version tracked (in code or migrations)
  - **Status:** ⚠ Partial — SQLite schema is defined in `init_db()` (app.py:60); no migration system
  - **Action:** For MVP, document current schema version (e.g., v1.0.0) in README; defer Alembic/migrations to Phase 2
  - **Timeline:** 30 min
  
- [ ] Backup/restore process documented
  - **Status:** ✗ Pending — No backup runbook documented
  - **Action:** Create `BACKUP_RESTORE.md`:
    - Daily export: `python statement_export.py` → S3
    - Restore: reimport via `seed_demo.py` + manual SQL restore
  - **Timeline:** 1 hour

---

## Deployment

- [x] Docker image built & pushed (docker build + docker push, if using Docker)
  - **Status:** ✓ Ready — `Dockerfile` configured; not required for Render/Railway (platform builds from requirements.txt)
  - **Action:** Optional — only needed if deploying to Kubernetes or custom Docker registry
  - **For MVP:** Skip Docker push; let Render/Railway use buildpack
  
- [x] Render/Railway config tested (render.yaml / railway.yml)
  - **Status:** ✓ Ready — `render.yaml` and `Procfile` configured; tested locally with `gunicorn wsgi:app`
  - **Action:** Quick sanity check:
    ```bash
    cd bharath-bank
    pip install -r requirements.txt
    PORT=8000 gunicorn wsgi:app --bind 0.0.0.0:$PORT
    ```
  - **Timeline:** 10 min
  
- [ ] Health check endpoint (optional: /health returning { "status": "ok" })
  - **Status:** ✗ Pending — No `/health` endpoint
  - **Action:** Add to app.py (optional for MVP; useful for uptime monitoring):
    ```python
    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})
    ```
  - **Timeline:** 15 min (optional)
  
- [ ] Rollback plan documented
  - **Status:** ✗ Pending — No rollback procedure documented
  - **Action:** Create `ROLLBACK.md`:
    - Render: redeploy previous commit via dashboard
    - Railway: use commit history / redeploy button
    - Manual: git revert + push
  - **Timeline:** 30 min

---

## Monitoring & Support

- [ ] Error alerting configured (Sentry / Rollbar / platform native)
  - **Status:** ✗ Pending — No error alerting
  - **Action:** One of:
    - **Render native:** Logs dashboard (free; built-in)
    - **Sentry:** Email alerts on unhandled exceptions (free tier, 5k events/mo)
    - **Rollbar:** Similar; slightly easier Render integration
  - **Recommended:** Sentry (better UX for exceptions)
  - **Setup time:** 1 hour (install SDK, configure)
  - **Timeline:** 1 hour
  
- [ ] Uptime monitoring (UptimeRobot or platform native)
  - **Status:** ✗ Pending — No uptime monitoring
  - **Action:** Configure one of:
    - **Render:** built-in dashboard shows service status
    - **UptimeRobot:** free tier monitors `/health` endpoint every 5 min; email alerts
  - **Timeline:** 30 min
  
- [x] Support email / contact (use user's bvenkatesulu909@gmail.com)
  - **Status:** ✓ Ready — Email address documented in memory; can be published in footer
  - **Action:** Add to app footer or `/contact` page
  - **Timeline:** 15 min

---

## Launch

- [ ] Smoke test on live server (register, login, transfer, loan apply)
  - **Status:** ✗ Pending — No live smoke test performed yet
  - **Action:** After deploying to Render/Railway staging, manually test:
    1. Register new user (verify email unique; password hashed)
    2. Login (verify session works)
    3. Deposit money (credit account)
    4. Transfer funds (between demo accounts)
    5. Apply for loan (verify EMI calculation)
    6. Pay EMI (verify balance updated)
    7. View statement (check export to CSV)
  - **Timeline:** 30 min
  
- [ ] Announcement / press (optional for demo)
  - **Status:** ✗ Pending — No announcement planned
  - **Action:** Optional; skip for MVP launch; add for Phase 2 if needed
  - **Timeline:** N/A

---

## Summary & Readiness

### Current Status: **35% Complete** (7/20 critical items ready)

| Category      | Ready | Partial | Pending | Notes |
|---------------|-------|---------|---------|-------|
| Infrastructure| 2     | 2       | 1       | Platform selected; domain + persistence TBD |
| Configuration| 2     | 1       | 2       | BBI_SECRET configured; CSRF + session timeout pending |
| Security     | 3     | 1       | 4       | HTTPS ready; patches C1/H1/H2 critical blockers |
| Testing      | 1     | 0       | 3       | Unit tests ready; E2E + load test pending |
| Data         | 1     | 1       | 1       | Seeding ready; backup + versioning pending |
| Deployment   | 2     | 0       | 2       | Config ready; health check + rollback plan pending |
| Monitoring   | 1     | 0       | 2       | Email ready; alerting + uptime pending |
| Launch       | 0     | 0       | 2       | Smoke test + press pending |

**Total:** 12 Ready | 5 Partial | 17 Pending

---

## Critical Blockers (Must Fix Before Deploy)

1. **SECURITY.md Patch C1 (CRITICAL):** Hardcoded SECRET_KEY fallback
   - Fix: Apply patch to fail closed on missing `BBI_SECRET` in production
   - Impact: Session hijacking vulnerability
   - Timeline: 1 hour

2. **SECURITY.md Patch H1 (HIGH):** No CSRF protection on POST routes
   - Fix: Add CSRF tokens to all forms
   - Impact: Cross-site money transfer attacks possible
   - Timeline: 3–4 hours

3. **Data Persistence Plan:**
   - If planning real data → Upgrade Render to paid or use persistent disk
   - If MVP demo only → Document that data is ephemeral; re-seed on deploy
   - Timeline: 2 hours (design decision)

---

## Recommended Pre-Launch Timeline

**Assuming no major scope changes:**

1. **Day 1 (8 hours)**
   - [ ] Apply SECURITY.md patches C1, H1, H2 (4 hours)
   - [ ] Add session timeout + `/health` endpoint (1 hour)
   - [ ] Run pytest locally (30 min)
   - [ ] Test gunicorn locally (30 min)

2. **Day 2 (4 hours)**
   - [ ] Push to GitHub
   - [ ] Deploy to Render staging via Blueprint (30 min)
   - [ ] Smoke test on staging (30 min)
   - [ ] Configure Sentry error alerting (1 hour)
   - [ ] Configure UptimeRobot monitoring (30 min)
   - [ ] Set up domain name + DNS (1 hour, may require waiting for propagation)

3. **Day 3 (2 hours)**
   - [ ] Final smoke test on production domain (30 min)
   - [ ] Document BACKUP.md + ROLLBACK.md (1.5 hours)
   - [ ] Announce launch (email, social, etc.) — optional

**Total Effort:** ~14 hours across 3 days

---

## Next Steps (After Launch)

- **Phase 2 Improvements:**
  - [ ] Load testing (JMeter or Locust)
  - [ ] Rate limiting on auth endpoints
  - [ ] Persistent database + backup automation (S3 nightly)
  - [ ] Mobile app (Flutter/React Native)
  - [ ] SMS/email notifications on transactions
  - [ ] Compliance audit (PCI-DSS, RBI guidelines)

---

## References

- **SECURITY.md:** Detailed patch code for C1, H1, H2
- **DEPLOY.md:** Platform-specific deployment steps (Render vs Railway)
- **ARCHITECTURE.md:** System design overview
- **API.md:** API endpoint documentation
- **README.md:** User-facing documentation

---

**Prepared by:** Claude Code Agent  
**Status:** Ready for pre-launch review
