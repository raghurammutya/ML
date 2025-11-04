# Ticker Service - Critical Issue Report

**Status**: 🔴 SERVICE DOWN
**Priority**: CRITICAL
**Assigned To**: Ticker Service Team
**Date**: November 4, 2025

---

## Issue Summary

Ticker service is failing to start due to configuration validation error.

**Exit Code**: 1
**Error Message**:
```
pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
  Value error, api_key must be set when api_key_enabled=True
```

---

## Impact

| Aspect | Impact Level | Details |
|--------|-------------|---------|
| **Service Status** | 🔴 CRITICAL | Service completely down |
| **User Impact** | 🔴 CRITICAL | No real-time market data available |
| **Affected Features** | 🔴 CRITICAL | - Real-time tick updates<br>- WebSocket streaming<br>- NIFTY monitor<br>- FO data streaming |
| **Business Impact** | 🔴 CRITICAL | Platform cannot operate without market data |

---

## Root Cause

The ticker service configuration has `api_key_enabled=True` but the `api_key` field is not set, causing Pydantic validation to fail during service initialization.

---

## How to Reproduce

```bash
# Check service status
docker ps -a | grep ticker

# View error logs
docker logs tv-ticker --tail 50

# Expected output:
# pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
#   Value error, api_key must be set when api_key_enabled=True
```

---

## Required Fix

Choose **ONE** of the following options:

### Option A: Set Valid API Key (If authentication required)

1. **Check current configuration**:
   ```bash
   cd /home/stocksadmin/Quantagro/tradingview-viz/ticker_service
   cat .env | grep API_KEY
   # OR check docker-compose.yml
   cat ../docker-compose.yml | grep -A 30 ticker_service
   ```

2. **Set API key** in `.env` or `docker-compose.yml`:
   ```bash
   # In .env file:
   API_KEY=your_secure_api_key_here
   API_KEY_ENABLED=true
   ```

   ```yaml
   # OR in docker-compose.yml:
   ticker_service:
     environment:
       - API_KEY=your_secure_api_key_here
       - API_KEY_ENABLED=true
   ```

3. **Restart service**:
   ```bash
   docker-compose stop ticker_service
   docker-compose build ticker_service
   docker-compose up -d ticker_service
   ```

4. **Verify startup**:
   ```bash
   # Check logs for successful startup
   docker logs tv-ticker --tail 50 --follow

   # Should see: "Ticker service started successfully" (or similar)

   # Test health endpoint
   curl http://localhost:8080/health

   # Expected: {"status": "ok", ...}
   ```

---

### Option B: Disable API Key Authentication (If not required)

1. **Check current configuration**:
   ```bash
   cd /home/stocksadmin/Quantagro/tradingview-viz/ticker_service
   cat .env | grep API_KEY
   ```

2. **Disable API key authentication** in `.env` or `docker-compose.yml`:
   ```bash
   # In .env file:
   API_KEY_ENABLED=false
   # Remove or comment out API_KEY line
   ```

   ```yaml
   # OR in docker-compose.yml:
   ticker_service:
     environment:
       - API_KEY_ENABLED=false
   ```

3. **Restart service**:
   ```bash
   docker-compose stop ticker_service
   docker-compose rm -f ticker_service
   docker-compose up -d ticker_service
   ```

4. **Verify startup**:
   ```bash
   docker logs tv-ticker --tail 50 --follow
   curl http://localhost:8080/health
   ```

---

## Success Criteria

- [ ] Ticker service starts without errors
- [ ] Container status shows "Up" (not "Exited")
- [ ] Health endpoint responds with HTTP 200
- [ ] WebSocket endpoint accepts connections
- [ ] No validation errors in logs

---

## Verification Commands

```bash
# 1. Check container status
docker ps | grep ticker
# Expected: Should show "Up" status, not "Exited"

# 2. Check logs for errors
docker logs tv-ticker --tail 50
# Expected: No ValidationError messages

# 3. Test health endpoint
curl -s http://localhost:8080/health | jq '.'
# Expected: {"status": "ok", ...}

# 4. Test WebSocket endpoint (optional)
curl -s -X POST http://localhost:8080/subscriptions \
  -H "Content-Type: application/json" \
  -d '{"instrument_token": 256265, "requested_mode": "FULL"}'
# Expected: Subscription created successfully

# 5. Verify data flowing to backend
curl -s http://localhost:8081/monitor/snapshot | jq '.underlying'
# Expected: Should show NIFTY data with price, volume, etc.
```

---

## Configuration Reference

**Files to Check**:
1. `/home/stocksadmin/Quantagro/tradingview-viz/ticker_service/.env`
2. `/home/stocksadmin/Quantagro/tradingview-viz/ticker_service/config.py` (or `settings.py`)
3. `/home/stocksadmin/Quantagro/tradingview-viz/docker-compose.yml`

**Relevant Environment Variables**:
```bash
API_KEY_ENABLED=true    # or false
API_KEY=<your_key>      # Required only if API_KEY_ENABLED=true
TICKER_SERVICE_PORT=8080
```

---

## Additional Notes

**Security Considerations** (if setting API key):
- Use a strong, randomly generated API key
- Store API key securely (not in git)
- Consider using Docker secrets or vault for production

**Testing Recommendations**:
1. After fix, test WebSocket subscriptions
2. Verify market data flowing to backend
3. Check that NIFTY monitor receives updates
4. Monitor logs for 10-15 minutes to ensure stability

---

## Time Estimate

- **Option A (Set API key)**: 15-20 minutes
- **Option B (Disable auth)**: 10-15 minutes

---

## Contact

**Reported By**: Backend Release Team
**Blocking**: Backend production release
**Urgency**: IMMEDIATE - Platform non-operational without this service

**Questions?** Check the full assessment: `/mnt/stocksblitz-data/Quantagro/tradingview-viz/PRODUCTION_READINESS_ASSESSMENT.md`

---

## Status Tracking

- [ ] Issue acknowledged by ticker service team
- [ ] Configuration option selected (A or B)
- [ ] Configuration updated
- [ ] Service restarted
- [ ] Verification tests passed
- [ ] Issue resolved and closed

**Last Updated**: November 4, 2025
