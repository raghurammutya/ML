# Alert Service - Backend API Integration Guide

**Quick Reference for Alert Service Development**

---

## Getting Started - 3 Steps

### Step 1: Get an API Key
```bash
# Contact backend team to create an API key with read permissions
# Format: Authorization: Bearer sb_abc123_xyz789...
# Store securely in environment variables (not in code)
```

### Step 2: Test Connection
```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
  http://localhost:8000/accounts/user123/positions
```

### Step 3: Implement Error Handling
```python
# Handle these HTTP responses:
- 200: Success - proceed normally
- 401: Invalid/expired API key - refresh or alert user
- 403: Permission denied - check key permissions
- 404: Resource not found - check account_id
- 429: Rate limited - implement exponential backoff
- 500: Server error - implement retry logic
```

---

## Core Endpoints for Alert Service

### 1. Get Positions (for P&L based alerts)
```
GET /accounts/{account_id}/positions
Authorization: Bearer <api_key>
```
**Use for:** Monitoring open position P&L, quantity changes

**Response:**
```json
{
  "status": "success",
  "account_id": "user123",
  "total_pnl": 5000.50,
  "positions": [
    {
      "tradingsymbol": "NIFTY25NOVFUT",
      "quantity": 50,
      "average_price": 19500,
      "last_price": 19625.50,
      "pnl": 6275,
      "day_pnl": 1200.75
    }
  ]
}
```

### 2. Get Orders (for execution tracking)
```
GET /accounts/{account_id}/orders?status=COMPLETE&limit=100
Authorization: Bearer <api_key>
```
**Use for:** Track order fills, trigger follow-up orders

**Response Fields:**
- order_id, tradingsymbol, status, filled_quantity, average_price

### 3. Get Funds/Margins
```
GET /accounts/{account_id}/funds?segment=equity
Authorization: Bearer <api_key>
```
**Use for:** Monitor available margin, trigger margin alerts

**Response:**
```json
{
  "status": "success",
  "funds": {
    "available_balance": 50000,
    "used_margin": 30000,
    "net_holdings": 100000
  }
}
```

### 4. Get Greeks Data
```
GET /fo/instruments/search
  ?symbol=NIFTY
  &segment=NFO-OPT
  &expiry_from=2025-11-01
Authorization: Bearer <api_key>
```
**Use for:** Greeks-based alerts (IV, Delta, Gamma, Theta, Vega)

**Available Greeks:**
- IV (Implied Volatility)
- Delta, Gamma, Theta, Vega
- Open Interest, Put-Call Ratio
- Max Pain levels

### 5. Check Market Hours
```
GET /calendar/status?calendar_code=NSE&date=2025-11-01
Authorization: Bearer <api_key>
```
**Use for:** Only trigger alerts during trading hours

**Response Fields:**
- is_trading_day, is_holiday, session_start, session_end, current_session

---

## WebSocket Endpoints (Real-time Updates)

### Connect to Order Updates
```javascript
// Connect with API key in query parameter
const ws = new WebSocket(
  'ws://localhost:8000/orders/user123?api_key=YOUR_API_KEY'
);

ws.onmessage = (event) => {
  const update = JSON.parse(event.data);
  console.log('Order update:', update);
  // Trigger alert if conditions met
};
```

### Connect to Greeks Updates
```javascript
const ws = new WebSocket(
  'ws://localhost:8000/fo/stream?api_key=YOUR_API_KEY'
);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  // Monitor IV changes, delta shifts, etc.
};
```

---

## Python Implementation Template

```python
import aiohttp
import asyncio
import json
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class BackendAPIClient:
    def __init__(self, api_key: str, base_url: str = "http://localhost:8000"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, *args):
        await self.session.close()
    
    async def get_positions(self, account_id: str):
        """Get current positions with P&L"""
        url = f"{self.base_url}/accounts/{account_id}/positions"
        async with self.session.get(url, headers=self.headers) as resp:
            if resp.status == 200:
                return await resp.json()
            elif resp.status == 401:
                logger.error("Invalid API key")
                raise Exception("API key authentication failed")
            elif resp.status == 404:
                logger.error(f"Account {account_id} not found")
                raise Exception(f"Account not found: {account_id}")
            else:
                raise Exception(f"API error: {resp.status}")
    
    async def get_funds(self, account_id: str, segment: str = "equity"):
        """Get available margin and funds"""
        url = f"{self.base_url}/accounts/{account_id}/funds?segment={segment}"
        async with self.session.get(url, headers=self.headers) as resp:
            return await resp.json()
    
    async def get_orders(self, account_id: str, status: str = None, limit: int = 100):
        """Get account orders"""
        params = f"?limit={limit}"
        if status:
            params += f"&status={status}"
        url = f"{self.base_url}/accounts/{account_id}/orders{params}"
        async with self.session.get(url, headers=self.headers) as resp:
            return await resp.json()
    
    async def search_fo_instruments(self, symbol: str, option_type: str = None):
        """Search options/futures for Greeks data"""
        params = f"?symbol={symbol}"
        if option_type:
            params += f"&option_type={option_type}"
        url = f"{self.base_url}/fo/instruments/search{params}"
        async with self.session.get(url, headers=self.headers) as resp:
            return await resp.json()
    
    async def check_market_hours(self, calendar_code: str = "NSE"):
        """Check if market is open"""
        from datetime import date
        today = date.today().isoformat()
        url = f"{self.base_url}/calendar/status?calendar_code={calendar_code}&date={today}"
        async with self.session.get(url, headers=self.headers) as resp:
            return await resp.json()
    
    async def stream_orders(self, account_id: str, callback):
        """WebSocket stream for order updates"""
        ws_url = f"ws://localhost:8000/orders/{account_id}?api_key={self.api_key}"
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(ws_url) as ws:
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        await callback(data)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error(f"WebSocket error: {ws.exception()}")
                        break


# Usage example
async def main():
    api_key = "YOUR_API_KEY"
    
    async with BackendAPIClient(api_key) as client:
        # Get positions
        positions = await client.get_positions("user123")
        print(f"Positions: {positions['positions']}")
        print(f"Total P&L: {positions['total_pnl']}")
        
        # Check margin
        funds = await client.get_funds("user123")
        available = funds['funds']['available_balance']
        print(f"Available margin: {available}")
        
        # Stream order updates
        async def on_order_update(data):
            print(f"Order update: {data}")
        
        # This will run indefinitely
        # await client.stream_orders("user123", on_order_update)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Alert Evaluation Logic Example

```python
async def evaluate_pnl_alert(client: BackendAPIClient, account_id: str, 
                             trigger: AlertTrigger):
    """
    Evaluate if a P&L based alert should trigger
    
    Args:
        trigger: {
            "type": "pnl_alert",
            "account_id": "user123",
            "condition": "total_pnl > 10000",
            "alert_id": "alert_123"
        }
    """
    positions = await client.get_positions(account_id)
    total_pnl = positions.get('total_pnl', 0)
    
    # Parse condition (simple example - use expression parser in production)
    if trigger['condition'] == "total_pnl > 10000":
        if total_pnl > 10000:
            return AlertEvent(
                alert_id=trigger['alert_id'],
                triggered_at=datetime.now(),
                condition_met=True,
                current_value=total_pnl,
                message=f"P&L exceeded threshold: {total_pnl}"
            )
    
    return None


async def evaluate_margin_alert(client: BackendAPIClient, account_id: str,
                               trigger: AlertTrigger):
    """Evaluate margin-based alert"""
    funds = await client.get_funds(account_id)
    available = funds['funds']['available_balance']
    
    if trigger['condition'] == "available < 5000":
        if available < 5000:
            return AlertEvent(
                alert_id=trigger['alert_id'],
                triggered_at=datetime.now(),
                current_value=available,
                message=f"Margin low: {available} remaining"
            )
    
    return None


async def evaluate_greeks_alert(client: BackendAPIClient,
                               trigger: AlertTrigger):
    """
    Evaluate Greeks-based alert
    
    Example trigger:
    {
        "type": "greeks_alert",
        "symbol": "NIFTY",
        "greek": "iv",
        "condition": "iv > 20",
        "expiry": "2025-11-30"
    }
    """
    instruments = await client.search_fo_instruments(
        symbol=trigger['symbol'],
        option_type="CE"
    )
    
    # Check if IV condition is met
    # (Actual implementation depends on response structure)
    
    return None
```

---

## Configuration Checklist

Before deploying alert service, ensure:

- [ ] API key created in backend with `can_read: True` permission
- [ ] API key stored in environment variable (not in code)
- [ ] Alert service added to CORS origins in backend config
- [ ] Error handling implemented for all HTTP responses
- [ ] WebSocket reconnection logic with exponential backoff
- [ ] Rate limit handling (max 200 requests/min)
- [ ] Logging configured for debugging
- [ ] Health check endpoint implemented
- [ ] Database schema for storing alert triggers
- [ ] Notification system (email/Slack/SMS) implementation

---

## Troubleshooting Common Issues

### "401 Unauthorized"
- Verify API key is correct
- Check Authorization header format: `Bearer <key>`
- API key might be expired or revoked

### "403 Forbidden"
- API key doesn't have required permissions
- Contact backend admin to grant `can_read` permission

### "404 Not Found"
- Account ID doesn't exist
- Verify account_id format and spelling

### "429 Too Many Requests"
- Exceeded rate limit (200 req/min default)
- Implement exponential backoff
- Consider caching positions/orders locally

### WebSocket Connection Drops
- Implement reconnection logic with exponential backoff
- Start with 1 second delay, max 60 seconds
- Check network connectivity
- Monitor logs for "Connection closed" messages

### Greeks Data Not Available
- Verify symbol exists (e.g., "NIFTY", "BANKNIFTY")
- Check expiry date is valid
- Ensure segment is correct (NFO-OPT, NFO-FUT)

---

## Performance Tips

1. **Cache frequently accessed data:**
   - Market hours (cache for entire day)
   - Instrument registry (cache for 1 hour)
   - Current margin (cache for 5 minutes)

2. **Use WebSocket for real-time updates:**
   - Don't poll positions every second
   - Connect to `/orders/{account_id}` for order updates
   - Connect to `/fo/stream` for Greeks updates

3. **Batch operations when possible:**
   - Use `/accounts/{account_id}/orders?limit=100` to get multiple orders
   - Filter at API level, not in alert service

4. **Implement request timeout:**
   - Set timeout to 10-15 seconds
   - Implement circuit breaker after 3 consecutive failures

---

## Production Deployment

### Environment Variables Required
```bash
BACKEND_API_URL=http://backend.service.com:8000
BACKEND_API_KEY=sb_xxx_yyy...
LOG_LEVEL=info
```

### Health Check
```bash
# Alert service should expose health endpoint
GET /health
Response: {"status": "healthy", "backend": "connected"}
```

### Monitoring
- Track API response times
- Monitor WebSocket connection stability
- Alert if backend becomes unavailable
- Log all triggered alerts with timestamp and conditions

---

## Support & Documentation

**Full API Documentation:** `/mnt/stocksblitz-data/Quantagro/tradingview-viz/BACKEND_API_ANALYSIS.md`

**Backend Repository:** `backend/app/routes/`

**Contact:** Backend team for API key creation and permission management

