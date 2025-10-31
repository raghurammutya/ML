# Deployment Runbook: FO OI (Open Interest) Feature

**Version:** 1.0
**Date:** 2025-10-31
**Feature:** Enable Open Interest data in FO strike-distribution and moneyness-series endpoints

---

## Executive Summary

This deployment adds Open Interest (OI) data to FO API endpoints by:
1. Creating enriched database views that wrap TimescaleDB continuous aggregates
2. Updating application code to return OI values instead of None
3. Adding graceful error handling and comprehensive documentation

**Risk Level:** 🟡 **MEDIUM**
**Rollback Time:** < 5 minutes
**Downtime Required:** No (zero-downtime deployment)

---

## Pre-Deployment Checklist

### Database Prerequisites
- [ ] PostgreSQL/TimescaleDB accessible
- [ ] Database user has CREATE VIEW and SELECT permissions
- [ ] Continuous aggregates exist:
  - `fo_option_strike_bars_5min`
  - `fo_option_strike_bars_15min`
- [ ] Base table has OI columns:
  - `fo_option_strike_bars.call_oi_sum`
  - `fo_option_strike_bars.put_oi_sum`

### Application Prerequisites
- [ ] Backend running Python 3.12+
- [ ] asyncpg version 0.27.0+
- [ ] Docker/docker-compose available for container deployments

### Verification Prerequisites
- [ ] Access to database for query verification
- [ ] Access to API endpoints for testing
- [ ] Monitoring/alerting configured

---

## Deployment Steps

### Phase 1: Database Migration (5 minutes)

**Step 1.1:** Connect to production database
```bash
psql -h <PROD_DB_HOST> -U <DB_USER> -d stocksblitz_unified
```

**Step 1.2:** Run pre-migration verification
```sql
-- Verify continuous aggregates exist
SELECT COUNT(*) FROM fo_option_strike_bars_5min;
SELECT COUNT(*) FROM fo_option_strike_bars_15min;

-- Verify base table has OI columns
SELECT call_oi_sum, put_oi_sum
FROM fo_option_strike_bars
WHERE call_oi_sum > 0
LIMIT 1;
```

**Expected Results:**
- Both aggregates should have > 0 rows
- Base table should return actual OI values (not NULL)

**Step 1.3:** Run migration
```bash
psql -h <PROD_DB_HOST> -U <DB_USER> -d stocksblitz_unified \
  -f migrations/013_create_fo_enriched_views.sql
```

**Step 1.4:** Verify enriched views created
```sql
-- Check views exist
\d fo_option_strike_bars_5min_enriched
\d fo_option_strike_bars_15min_enriched

-- Verify OI columns present
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'fo_option_strike_bars_5min_enriched'
  AND column_name IN ('call_oi_sum', 'put_oi_sum');

-- Verify data
SELECT COUNT(*) FROM fo_option_strike_bars_5min_enriched
WHERE call_oi_sum > 0;
```

**Expected Results:**
- Both views should have 24 columns
- call_oi_sum and put_oi_sum should be type `double precision`
- At least 1 row with call_oi_sum > 0

**⚠️ STOP GATE:** Do not proceed if enriched views are missing or have no OI data.

---

### Phase 2: Application Deployment (10 minutes)

**Option A: Docker Deployment (Recommended)**

```bash
cd /path/to/tradingview-viz/backend

# Step 2.1: Stop existing container
docker-compose stop backend

# Step 2.2: Rebuild with new code
docker-compose build backend

# Step 2.3: Start backend
docker-compose up -d backend

# Step 2.4: Wait for health check
sleep 10
curl http://localhost:8081/health
```

**Option B: Non-Docker Deployment**

```bash
cd /path/to/tradingview-viz/backend

# Step 2.1: Pull latest code
git pull origin main  # or your deployment branch

# Step 2.2: Restart application (adjust for your setup)
systemctl restart tradingview-backend
# OR
supervisorctl restart tradingview-backend
# OR
pkill -9 -f "uvicorn.*main:app" && uvicorn app.main:app &
```

**Step 2.5:** Verify application started
```bash
# Check logs for errors
docker-compose logs backend --tail=100 | grep -i error

# Check health endpoint
curl http://localhost:8081/health
```

**Expected Results:**
- Health check returns `{"status": "healthy"}`
- No errors in logs related to missing columns or views

---

### Phase 3: Verification (5 minutes)

**Step 3.1:** Test strike-distribution endpoint
```bash
curl -s "http://localhost:8081/fo/strike-distribution?symbol=NIFTY50&timeframe=5&expiry=2025-11-04" \
  | python3 -c "import sys, json; d=json.load(sys.stdin); print('OI values:', d['series'][0]['points'][0]['call_oi'], d['series'][0]['points'][0]['put_oi'])"
```

**Expected:** OI values > 0 (e.g., `OI values: 14.0 12.0`)

**Step 3.2:** Test moneyness-series endpoint
```bash
# Get current timestamp (adjust timezone)
FROM_TS=$(date -u -d '6 hours ago' +%s)
TO_TS=$(date -u +%s)

curl -s "http://localhost:8081/fo/moneyness-series?symbol=NIFTY50&timeframe=5&indicator=oi&expiry=2025-11-04&from=${FROM_TS}&to=${TO_TS}" \
  | python3 -c "import sys, json; d=json.load(sys.stdin); print('Series count:', len(d['series'])); print('First point value:', d['series'][0]['points'][0]['value'] if d['series'] else 'EMPTY')"
```

**Expected:**
- Series count > 0
- First point value > 0

**Step 3.3:** Test other indicators still work
```bash
curl -s "http://localhost:8081/fo/strike-distribution?symbol=NIFTY50&timeframe=5&expiry=2025-11-04&indicator=iv" \
  | python3 -c "import sys, json; d=json.load(sys.stdin); print('IV working:', len(d['series']) > 0)"
```

**Expected:** `IV working: True`

**Step 3.4:** Check database query performance
```sql
EXPLAIN ANALYZE
SELECT * FROM fo_option_strike_bars_5min_enriched
WHERE symbol = 'NIFTY50'
  AND expiry = '2025-11-04'
  AND bucket_time > NOW() - INTERVAL '6 hours'
LIMIT 100;
```

**Expected:** Query execution time < 100ms

**⚠️ STOP GATE:** If any verification fails, proceed to rollback immediately.

---

## Rollback Procedure

**Time Required:** < 5 minutes

### Step R1: Revert Application Code
```bash
# For Docker deployments
docker-compose stop backend
docker-compose build backend --build-arg GIT_REF=<PREVIOUS_COMMIT>
docker-compose up -d backend

# For git deployments
git revert <COMMIT_HASH>
systemctl restart tradingview-backend
```

### Step R2: Drop Enriched Views (Optional)
Only needed if views cause database performance issues:
```bash
psql -h <PROD_DB_HOST> -U <DB_USER> -d stocksblitz_unified \
  -f migrations/013_rollback_fo_enriched_views.sql
```

### Step R3: Verify Rollback
```bash
curl http://localhost:8081/health
```

Expected: Application returns to previous behavior (OI endpoints may return 0 or empty, but no errors)

---

## Monitoring

### Key Metrics to Monitor

1. **API Response Times**
   - `/fo/strike-distribution` should remain < 500ms
   - `/fo/moneyness-series` should remain < 1000ms

2. **Database Query Performance**
   - Monitor slow query logs for `fo_option_strike_bars_5min_enriched`
   - Alert if query time > 1 second

3. **Error Rates**
   - Monitor for "OI column not found" warnings
   - Monitor for 500 errors on FO endpoints

4. **Data Quality**
   - Sample OI values should be > 0
   - Compare OI values with ticker service data

### Recommended Alerts

```yaml
# Example Prometheus alert rules
- alert: FOEndpointHighLatency
  expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{endpoint=~"/fo/.*"}[5m])) > 1
  for: 5m

- alert: FOEndpointErrors
  expr: rate(http_requests_total{endpoint=~"/fo/.*", status=~"5.."}[5m]) > 0.01
  for: 2m

- alert: OIDataMissing
  expr: fo_oi_zero_count_total > 100
  for: 5m
```

---

## Troubleshooting

### Issue 1: "OI column not found" warnings in logs

**Symptom:** API returns OI=0, logs show `OI column not found in row - enriched views may be missing`

**Diagnosis:**
```sql
SELECT * FROM information_schema.views
WHERE table_name LIKE '%enriched%';
```

**Fix:** Run migration 013 if views are missing

---

### Issue 2: Slow query performance

**Symptom:** API response times > 1 second

**Diagnosis:**
```sql
EXPLAIN ANALYZE
SELECT * FROM fo_option_strike_bars_5min_enriched
WHERE symbol = 'NIFTY50' AND expiry = '2025-11-04'
  AND bucket_time > NOW() - INTERVAL '6 hours';
```

**Fix:** Add covering index:
```sql
CREATE INDEX IF NOT EXISTS idx_fo_strike_1min_join
ON fo_option_strike_bars (symbol, expiry, strike, bucket_time)
WHERE timeframe = '1min';
```

---

### Issue 3: OI values are 0 despite database having data

**Symptom:** `call_oi: 0, put_oi: 0` in API response

**Diagnosis:**
```bash
# Check if backend is using old code
docker exec tv-backend grep -A 3 'if indicator == "oi":' /app/app/routes/fo.py
```

**Expected:** Should see `return row.get("call_oi_sum")` not `return None`

**Fix:** Rebuild backend container to pick up latest code

---

## Performance Benchmarks

### Expected Performance (Post-Deployment)

| Endpoint | P50 | P95 | P99 |
|----------|-----|-----|-----|
| /fo/strike-distribution | 150ms | 400ms | 800ms |
| /fo/moneyness-series | 300ms | 800ms | 1500ms |

### Database Query Performance

| Query | Rows | Execution Time |
|-------|------|----------------|
| SELECT * FROM fo_option_strike_bars_5min_enriched (6hr window) | ~1000 | 30-80ms |
| SELECT * FROM fo_option_strike_bars_5min_enriched (24hr window) | ~4000 | 100-200ms |

**Note:** Times measured on development environment. Production may vary based on hardware.

---

## Post-Deployment Tasks

### Within 24 Hours
- [ ] Monitor error rates and response times
- [ ] Verify OI data matches expectations
- [ ] Review slow query logs
- [ ] Update API documentation if needed

### Within 1 Week
- [ ] Analyze query performance under production load
- [ ] Consider adding indexes if slow queries detected
- [ ] Review frontend integration (if applicable)
- [ ] Update runbook based on lessons learned

---

## Approval Sign-Off

| Role | Name | Signature | Date |
|------|------|-----------|------|
| **Developer** | | | |
| **Tech Lead** | | | |
| **Release Manager** | | | |
| **Database Admin** | | | |

---

## References

- Migration File: `migrations/013_create_fo_enriched_views.sql`
- Rollback File: `migrations/013_rollback_fo_enriched_views.sql`
- Code Changes:
  - `app/routes/fo.py:379-422` (_indicator_value function)
  - `app/database.py:142-154` (FO_STRIKE_TABLES configuration)
- Documentation:
  - `FOSTREAM_COMPLETE_STATUS.md` (data pipeline status)
  - `DATA_PIPELINE_COMPLETE_STATUS.md` (API issues and fixes)

---

**Last Updated:** 2025-10-31
**Version:** 1.0
**Document Owner:** Backend Team
