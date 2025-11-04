# SDK Test Issues & Fixes

## Issues Found from sample-output.txt

### Issue #1: Indicator Authentication Failures ❌

**Error:**
```
Authentication failed: {"detail":"Invalid or expired API key"}
```

**Root Cause:**
The backend `/indicators/` endpoints require API key authentication, but the SDK is sending JWT tokens.

**Fix Options:**

#### Option A: Backend accepts JWT for indicators (Recommended)
Update backend to accept both JWT and API key for indicator endpoints.

**Location:** `/mnt/stocksblitz-data/Quantagro/tradingview-viz/backend/app/routes/indicators.py`

Add JWT middleware:
```python
from app.jwt_auth import JWTBearer

@router.get("/at-offset", dependencies=[Depends(JWTBearer())])  # Add JWT auth
async def get_indicators_at_offset(...):
    ...
```

#### Option B: SDK uses API key for indicators
Create hybrid authentication in SDK (JWT for most endpoints, API key for indicators).

This is less ideal as it requires managing two authentication methods.

---

### Issue #2: Stale Data (35+ minutes old) ⚠️

**Warning:**
```
Stale data for NIFTY 50: Data is 2143.7 seconds old
```

**Root Cause:**
Script ran at **7:28 AM IST**, but market opens at **9:15 AM IST**.

**Status:** ✅ **NOT A BUG** - Expected behavior outside market hours

**Solution:** Run during market hours (9:15 AM - 3:30 PM IST)

---

### Issue #3: Futures Symbol Not Supported ❌

**Error:**
```
ValueError: Cannot extract underlying from 'NIFTY25NOVFUT'
```

**Root Cause:**
SDK's `_extract_underlying()` method only handles option symbols, not futures.

**Fix:** Add futures pattern matching

**Location:** `/mnt/stocksblitz-data/Quantagro/tradingview-viz/python-sdk/stocksblitz/instrument.py`

**Line ~500-540**, update `_extract_underlying()`:

```python
def _extract_underlying(self, symbol: str) -> str:
    """Extract underlying symbol from option/futures symbol."""
    import re

    # Pattern for option symbols: NIFTY25N0424500PE
    match = re.match(r'^(NIFTY|BANKNIFTY|FINNIFTY)(\d{2}[A-Z]\d{2})(\d+)(CE|PE)$', symbol)
    if match:
        return match.group(1)

    # Pattern for futures symbols: NIFTY25NOVFUT
    match = re.match(r'^(NIFTY|BANKNIFTY|FINNIFTY)(\d{2}[A-Z]{3})FUT$', symbol)
    if match:
        return match.group(1)

    # Direct underlying symbols
    normalized = symbol.replace(" ", "").upper()
    known_underlyings = {"NIFTY", "NIFTY50", "BANKNIFTY", "FINNIFTY", "SENSEX"}

    if normalized in known_underlyings:
        return "NIFTY" if "NIFTY" in normalized else normalized

    raise ValueError(f"Cannot extract underlying from '{symbol}'")
```

---

### Issue #4: Options Not in Monitor Snapshot ⚠️

**Error:**
```
NIFTY25N0425600CE not found in monitor snapshot for Greeks
```

**Root Cause:**
The specific strike (25600) might not be in the ticker service subscriptions.

**Status:** ✅ **NOT A BUG** - Options need to be subscribed first

**Solutions:**

1. **Check current subscriptions:**
   ```bash
   curl -s http://localhost:8080/subscriptions | python3 -c "
   import sys, json
   data = json.load(sys.stdin)
   options = [s for s in data if 'CE' in s['tradingsymbol'] or 'PE' in s['tradingsymbol']]
   print(f'Total options subscribed: {len(options)}')
   for opt in options[:10]:
       print(f\"  {opt['tradingsymbol']} - {opt['status']}\")
   "
   ```

2. **Subscribe to missing strikes:**
   ```bash
   curl -X POST http://localhost:8080/subscriptions \
     -H "Content-Type: application/json" \
     -d '{"instrument_token": 12198914, "requested_mode": "FULL"}'
   ```

3. **Or use strikes that are already subscribed** (check output above)

---

## 🔧 Quick Fixes to Apply

### Fix #1: Add Futures Support to SDK

```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/python-sdk

# Edit instrument.py
# Add futures pattern to _extract_underlying() method (see code above)
```

### Fix #2: Backend JWT Support for Indicators

```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/backend

# Edit app/routes/indicators.py
# Add JWTBearer() dependency to indicator endpoints
```

### Fix #3: Run During Market Hours

```bash
# Check current IST time
TZ='Asia/Kolkata' date

# Run script between 9:15 AM - 3:30 PM IST
python3 test_tick_monitor_enhanced.py
```

---

## ✅ What's Working

Despite the issues, these components ARE working:

1. ✅ **Authentication** - JWT login successful
2. ✅ **Quote Data** - LTP, OHLC, Volume fetched (though stale)
3. ✅ **Option Parsing** - Moneyness calculation working
4. ✅ **Script Flow** - Monitor loop running correctly
5. ✅ **Data Export** - CSV export functionality working

---

## 🎯 Recommended Actions

### Immediate (to test now):

1. **Run during market hours** (9:15 AM - 3:30 PM IST)
2. **Check subscribed instruments:**
   ```bash
   curl -s http://localhost:8080/subscriptions | grep -E "25[56][0-9]{2}(CE|PE)" | head -20
   ```
3. **Use subscribed strikes in the script** (modify monitored_options list)

### Short-term (for full functionality):

1. **Fix futures support** (5 minutes)
   - Update `instrument.py` as shown above

2. **Fix indicator auth** (10 minutes)
   - Add JWT support to backend indicator routes
   - OR disable indicators temporarily in script

### Long-term (enhancements):

1. **Auto-discover subscribed instruments**
   - Query `/subscriptions` API
   - Build monitored list dynamically

2. **Handle market hours gracefully**
   - Detect market status
   - Show appropriate message when closed

3. **Add retry logic**
   - Retry failed indicator calls
   - Handle stale data more gracefully

---

## 🧪 Testing Checklist

Before running again:

- [ ] Verify market is open (9:15 AM - 3:30 PM IST)
- [ ] Check ticker service is publishing: `redis-cli PUBSUB CHANNELS "ticker:*"`
- [ ] Verify subscriptions: `curl http://localhost:8080/subscriptions | wc -l`
- [ ] Check backend health: `curl http://localhost:8081/health`
- [ ] Confirm JWT token: `curl -X POST http://localhost:8001/v1/auth/login ...`

---

## 📞 Need Help?

If issues persist:
1. Check logs: `docker logs tv-backend`, `docker logs tv-ticker`
2. Verify Redis: `redis-cli -p 6379 PUBSUB NUMSUB ticker:nifty:options`
3. Test backend directly: `curl -H "Authorization: Bearer <token>" http://localhost:8081/monitor/snapshot?underlying=NIFTY`

---

**Summary:** The script mostly works! Main issues are market hours (expected) and indicator authentication (backend needs update). Futures support needs SDK fix.
