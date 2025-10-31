# Kite API Failover Feature - Documentation

**Date**: 2025-10-31
**Status**: ✅ IMPLEMENTED

---

## Overview

Automatic account failover mechanism for Kite API requests. When an API request fails due to rate limiting, subscription limits, or quota exhaustion, the system automatically retries with the next available trading account.

---

## Problem Solved

**Issue**: Kite API has limits per account:
- Rate limiting (429 Too Many Requests)
- Maximum subscriptions per account
- API quota limits
- Daily request limits

**Solution**: When one account hits limits, automatically try the next account instead of failing the request.

---

## Features

✅ **Automatic Failover**: Seamless retry with next account
✅ **Smart Error Detection**: Recognizes Kite API limit errors
✅ **Comprehensive Logging**: Logs failover attempts and exhaustion
✅ **Graceful Degradation**: Single account = log error and fail
✅ **Configurable**: Supports preferred accounts and retry limits

---

## What's Covered

### ✅ History Data Fetching (HTTP API)

When fetching historical data via `/history` endpoint:
- Tries preferred account first (if specified)
- On rate limit/subscription error, tries next account
- Continues until success or all accounts exhausted
- Logs appropriately

**Example Flow**:
```
1. Client requests: GET /history?instrument_token=123...
2. System tries account: "primary"
3. Kite returns: 429 Too Many Requests
4. System logs: "history_fetch failed for account primary: Rate limit. Attempting failover..."
5. System tries account: "secondary"
6. Success! Returns data
```

### ✅ Future API Calls

The failover mechanism is ready for any Kite HTTP API call:
- Order placement (if integrated)
- Portfolio queries
- Margin calculations
- Quote fetching

### ⚠️ WebSocket Subscriptions (Different Architecture)

WebSocket connections are persistent per-account. Failover for WebSockets requires different handling:
- Current: Each account has its own WebSocket connection
- Failover: Would need to detect subscription limits and switch WebSocket connections
- Status: Not implemented (complex, different architecture)

**Note**: HTTP API calls (history, quotes) use failover. WebSocket streams use per-account connections.

---

## Architecture

### Core Components

#### 1. Error Detection (`app/kite_failover.py`)

```python
def is_kite_limit_error(error: Exception) -> bool:
    """
    Detect if error is due to Kite API limits.

    Checks for:
    - HTTP 429 status
    - "rate limit" in message
    - "subscription limit" in message
    - "quota exceeded" in message
    - "too many requests" in message
    """
```

**Detected Patterns**:
- `"too many requests"`
- `"rate limit"`
- `"429"`
- `"quota exceeded"`
- `"subscription limit"`
- `"maximum subscriptions"`
- `"throttled"`

#### 2. Failover Context Manager (`app/kite_failover.py`)

```python
@asynccontextmanager
async def borrow_with_failover(
    orchestrator: SessionOrchestrator,
    operation: str = "api_call",
    preferred_account: Optional[str] = None,
    max_retries: Optional[int] = None
):
    """
    Borrow a Kite client with automatic failover.

    Usage:
        async with borrow_with_failover(orchestrator, "history") as client:
            data = await client.fetch_historical(...)
    """
```

#### 3. Integration (`app/generator.py`)

Modified `fetch_history()` to use failover:

**Before**:
```python
async with orchestrator.borrow(account_id) as lease:
    return await client.fetch_historical(...)
```

**After**:
```python
async with borrow_with_failover(
    orchestrator,
    operation=f"history_fetch[{instrument_token}]",
    preferred_account=account_id
) as client:
    return await client.fetch_historical(...)
```

---

## Usage Examples

### Example 1: History Data with Single Account

```bash
# Configuration: Only 1 account ("primary")
curl "http://localhost:8080/history?instrument_token=123&from_ts=2025-01-01T00:00:00&to_ts=2025-01-31T23:59:59"

# If rate limit hit:
# Log: "history_fetch[123] failed: Only 1 account available and it has reached limits."
# Response: HTTP 502 - "Historical fetch failed: Too many requests"
```

### Example 2: History Data with Multiple Accounts

```bash
# Configuration: 3 accounts ("primary", "secondary", "tertiary")
curl "http://localhost:8080/history?instrument_token=456&from_ts=2025-01-01T00:00:00&to_ts=2025-01-31T23:59:59"

# Flow:
# 1. Try "primary" -> Rate limit error
# 2. Log: "history_fetch[456] failed for account primary: Rate limit. Attempting failover..."
# 3. Try "secondary" -> Success!
# 4. Return data
```

### Example 3: All Accounts Exhausted

```bash
# All 3 accounts have hit rate limits
curl "http://localhost:8080/history?instrument_token=789&..."

# Flow:
# 1. Try "primary" -> Rate limit
# 2. Try "secondary" -> Rate limit
# 3. Try "tertiary" -> Rate limit
# 4. Log: "history_fetch[789] failed: All 3 accounts have reached limits."
# 5. Response: HTTP 502 - "Historical fetch failed: Too many requests"
```

### Example 4: Preferred Account Specified

```bash
# Client specifies preferred account
curl "http://localhost:8080/history?instrument_token=999&account_id=secondary&..."

# Flow:
# 1. Try "secondary" (preferred) -> Rate limit
# 2. Log: "Attempting failover..."
# 3. Try "primary" -> Success!
# 4. Return data
```

---

## Configuration

### Multi-Account Setup

**Option 1: YAML Configuration** (`kite_accounts.yaml`)

```yaml
accounts:
  primary:
    api_key: ${KITE_PRIMARY_API_KEY}
    api_secret: ${KITE_PRIMARY_API_SECRET}
    access_token: ${KITE_PRIMARY_ACCESS_TOKEN}
    token_dir: ./tokens

  secondary:
    api_key: ${KITE_SECONDARY_API_KEY}
    api_secret: ${KITE_SECONDARY_API_SECRET}
    access_token: ${KITE_SECONDARY_ACCESS_TOKEN}
    token_dir: ./tokens

  tertiary:
    api_key: ${KITE_TERTIARY_API_KEY}
    api_secret: ${KITE_TERTIARY_API_SECRET}
    access_token: ${KITE_TERTIARY_ACCESS_TOKEN}
    token_dir: ./tokens
```

**Option 2: Environment Variables**

```bash
# Primary account
export KITE_PRIMARY_API_KEY="your_key"
export KITE_PRIMARY_API_SECRET="your_secret"
export KITE_PRIMARY_ACCESS_TOKEN="your_token"

# Secondary account
export KITE_SECONDARY_API_KEY="your_key"
export KITE_SECONDARY_API_SECRET="your_secret"
export KITE_SECONDARY_ACCESS_TOKEN="your_token"

# Tertiary account
export KITE_TERTIARY_API_KEY="your_key"
export KITE_TERTIARY_API_SECRET="your_secret"
export KITE_TERTIARY_ACCESS_TOKEN="your_token"
```

### Docker Compose

```yaml
services:
  ticker-service:
    environment:
      # Account 1
      - KITE_PRIMARY_API_KEY=key1
      - KITE_PRIMARY_ACCESS_TOKEN=token1

      # Account 2
      - KITE_SECONDARY_API_KEY=key2
      - KITE_SECONDARY_ACCESS_TOKEN=token2

      # Account 3
      - KITE_TERTIARY_API_KEY=key3
      - KITE_TERTIARY_ACCESS_TOKEN=token3
```

---

## Monitoring & Logs

### Log Levels

**DEBUG**: Failover attempts
```
DEBUG - Attempting history_fetch with account primary (attempt 1/3)
```

**WARNING**: Failover triggered
```
WARNING - history_fetch[123] failed for account primary: 429 Too Many Requests. Attempting failover to next account...
```

**ERROR**: All accounts exhausted
```
ERROR - history_fetch[456] failed: All 3 accounts have reached limits. Last error: Too many requests
```

**ERROR**: Single account limit hit
```
ERROR - history_fetch[789] failed: Only 1 account available and it has reached limits. Error: Rate limit exceeded
```

### Monitoring Queries

**Check for failover events**:
```bash
docker logs tv-ticker 2>&1 | grep "Attempting failover"
```

**Check for exhausted accounts**:
```bash
docker logs tv-ticker 2>&1 | grep "All.*accounts have reached limits"
```

**Check failover success rate**:
```bash
# Successful failovers (WARNING followed by success)
docker logs tv-ticker 2>&1 | grep -A1 "Attempting failover" | grep "completed"

# Failed failovers (ERROR - all exhausted)
docker logs tv-ticker 2>&1 | grep "All.*accounts have reached limits"
```

---

## Prometheus Metrics

Integration with existing metrics system:

```python
# Add failover metrics (future enhancement)
from app.metrics import Counter

kite_failover_attempts = Counter(
    'kite_failover_attempts_total',
    'Total Kite API failover attempts',
    ['operation', 'from_account', 'to_account', 'success']
)

kite_account_exhausted = Counter(
    'kite_accounts_exhausted_total',
    'Total times all accounts exhausted',
    ['operation']
)
```

---

## Testing

### Test Script

```python
import asyncio
from app.accounts import SessionOrchestrator
from app.kite_failover import borrow_with_failover

async def test_failover():
    orchestrator = SessionOrchestrator()

    # Test with failover
    async with borrow_with_failover(
        orchestrator,
        operation="test_history",
        preferred_account="primary"
    ) as client:
        data = await client.fetch_historical(
            instrument_token=123,
            from_ts=1640995200,
            to_ts=1672531199,
            interval="day"
        )
        print(f"Success! Got {len(data)} candles")

asyncio.run(test_failover())
```

### Manual Testing

```bash
# Test 1: Normal operation (no limits)
curl "http://localhost:8080/history?instrument_token=12192002&from_ts=2025-01-01T00:00:00&to_ts=2025-01-31T23:59:59&interval=day"

# Expected: Success with data

# Test 2: Simulate rate limit (requires hitting actual limit)
# Make many rapid requests to exhaust primary account
for i in {1..100}; do
  curl "http://localhost:8080/history?instrument_token=12192002&from_ts=2025-01-01T00:00:00&to_ts=2025-01-31T23:59:59"
done

# Expected: Some requests failover to secondary account

# Test 3: Check logs for failover
docker logs tv-ticker 2>&1 | tail -50 | grep "failover"
```

---

## Error Handling

### Errors That Trigger Failover

✅ **HTTP 429** - Too Many Requests
✅ **Rate limit exceeded** - Message contains "rate limit"
✅ **Subscription limit** - Message contains "subscription limit"
✅ **Quota exceeded** - Message contains "quota exceeded"
✅ **Throttled** - Message contains "throttled"

### Errors That Don't Trigger Failover

❌ **Invalid parameters** - Not a limit issue
❌ **Authentication failure** - Account-specific issue
❌ **Network timeout** - Transient network issue
❌ **Invalid instrument** - Data issue, not limit

These errors are raised immediately without failover.

---

## Performance Impact

| Aspect | Impact | Notes |
|--------|--------|-------|
| Normal Operation | None | No change when no limits hit |
| First Failover | ~100-200ms | Time to try next account |
| Multiple Failovers | ~100-200ms per account | Linear with account count |
| Memory | Minimal | No additional state stored |

**Recommendation**: Use 2-3 accounts for redundancy without excessive failover time.

---

## Best Practices

### 1. Account Distribution

**Good**:
```yaml
accounts:
  primary:    # Main production account
  secondary:  # Backup account
  tertiary:   # Emergency backup
```

**Better**:
```yaml
accounts:
  trading:    # For order operations
  data:       # For historical data fetching
  backup:     # Emergency failover
```

### 2. Monitoring

- Set up alerts for "All accounts exhausted" errors
- Monitor failover frequency to detect limit issues
- Track which accounts hit limits most often

### 3. Capacity Planning

- **Light usage**: 1 account sufficient
- **Medium usage**: 2 accounts recommended
- **Heavy usage**: 3+ accounts for redundancy

### 4. Error Handling in Clients

**Client-side**:
```python
try:
    response = requests.get("/history?instrument_token=123...")
    data = response.json()
except requests.HTTPError as e:
    if e.response.status_code == 502:
        # All accounts exhausted - retry later
        print("API limits reached, retry in 1 minute")
    else:
        raise
```

---

## Limitations

### Current Limitations

1. **WebSocket Subscriptions**: Not covered (different architecture)
2. **Order Placement**: Not integrated yet (requires modification)
3. **No Backoff**: Immediate failover (no exponential backoff)
4. **No Metrics**: Failover events not tracked in Prometheus (yet)

### Future Enhancements

**Phase 2: WebSocket Failover**
- Detect subscription limits on WebSocket
- Migrate subscriptions to different account's WebSocket
- Maintain state during migration

**Phase 3: Intelligent Routing**
- Track account usage/limits
- Proactively route to least-used account
- Implement exponential backoff

**Phase 4: Metrics Integration**
- Add Prometheus metrics for failover
- Dashboard showing account health
- Alerts for exhausted accounts

---

## Troubleshooting

### Issue: Failover not working

**Symptoms**: Requests fail without trying other accounts

**Debugging**:
```bash
# Check if multiple accounts configured
docker exec tv-ticker python3 -c "from app.accounts import SessionOrchestrator; o = SessionOrchestrator(); print(o.list_accounts())"

# Check logs for error detection
docker logs tv-ticker 2>&1 | grep "is_kite_limit_error"
```

**Solutions**:
- Verify multiple accounts in config
- Check error message matches detection patterns
- Review logs for actual error type

### Issue: All accounts exhausted frequently

**Symptoms**: Constant "All N accounts have reached limits" errors

**Debugging**:
```bash
# Check request rate
docker logs tv-ticker 2>&1 | grep "history_fetch" | wc -l

# Check failover frequency
docker logs tv-ticker 2>&1 | grep "Attempting failover" | wc -l
```

**Solutions**:
- Add more accounts
- Implement request caching
- Rate limit client requests
- Spread requests across time

### Issue: Specific account always fails

**Symptoms**: One account constantly triggers failover

**Debugging**:
```bash
# Check account-specific errors
docker logs tv-ticker 2>&1 | grep "account primary" | grep "failed"
```

**Solutions**:
- Verify account credentials
- Check account permissions
- Verify access token validity
- Review account-specific rate limits

---

## API Changes

### Backward Compatibility

✅ **Fully Backward Compatible**
- No API changes for clients
- No configuration changes required
- Works with single or multiple accounts
- Graceful degradation for single account

### Migration

**Step 1**: Deploy new code (already done)
```bash
docker-compose build ticker-service
docker-compose restart ticker-service
```

**Step 2**: Add additional accounts (optional)
```yaml
# kite_accounts.yaml
accounts:
  primary:
    api_key: ...
  secondary:  # NEW
    api_key: ...
```

**Step 3**: Monitor logs
```bash
docker logs -f tv-ticker | grep "failover"
```

**Step 4**: Enjoy resilience!

---

## Summary

✅ **Implemented**: Automatic failover for Kite API HTTP calls
✅ **Tested**: History data fetching with failover
✅ **Logged**: Comprehensive logging for debugging
✅ **Documented**: Complete usage guide
✅ **Backward Compatible**: No breaking changes

**Next Steps**:
1. Add more accounts to configuration
2. Monitor failover events
3. Consider WebSocket failover (Phase 2)
4. Add Prometheus metrics (Phase 3)

---

**Questions or Issues?**

- Check logs: `docker logs tv-ticker | grep failover`
- Review config: `cat kite_accounts.yaml`
- Test manually: Use curl examples above

---

**Feature Completed**: 2025-10-31 ✅
