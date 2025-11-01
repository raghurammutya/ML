# Getting Started with Alert Service

## Prerequisites

Before you start, ensure you have:

- ✅ Python 3.11 or higher
- ✅ PostgreSQL with TimescaleDB extension
- ✅ Redis running (optional for Phase 1)
- ✅ Telegram Bot Token: `8499559189:AAHjPsZHyCsI94k_H3pSJm1hg-d8rnisgSY`

## Quick Start (5 Minutes)

### Step 1: Run Database Migrations

```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/alert_service

# Verify TimescaleDB extension
psql -U stocksblitz -d stocksblitz_unified -f migrations/000_verify_timescaledb.sql

# Create alerts table
psql -U stocksblitz -d stocksblitz_unified -f migrations/001_create_alerts.sql

# Create alert_events table (TimescaleDB hypertable)
psql -U stocksblitz -d stocksblitz_unified -f migrations/002_create_alert_events.sql

# Create notification preferences and log tables
psql -U stocksblitz -d stocksblitz_unified -f migrations/003_create_notification_preferences.sql
```

**Expected output:**
```
TimescaleDB extension already exists.
CREATE TABLE
CREATE INDEX
...
SELECT 1
```

### Step 2: Install Dependencies

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Step 3: Start the Service

```bash
# Start with auto-reload (development)
uvicorn app.main:app --reload --port 8082

# Or start with multiple workers (production)
uvicorn app.main:app --host 0.0.0.0 --port 8082 --workers 2
```

**Expected output:**
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Database pool created: localhost:5432/stocksblitz_unified
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8082
```

### Step 4: Verify Installation

```bash
# Health check
curl http://localhost:8082/health

# Expected response
{
  "status": "ok",
  "timestamp": "2025-11-01T...",
  "service": "alert-service",
  "version": "1.0.0",
  "environment": "development",
  "database": "healthy"
}
```

### Step 5: Access API Documentation

Open in browser:
- **Swagger UI**: http://localhost:8082/docs
- **ReDoc**: http://localhost:8082/redoc

---

## Create Your First Alert

### Using cURL

```bash
curl -X POST http://localhost:8082/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "NIFTY 24000 breakout",
    "alert_type": "price",
    "priority": "high",
    "condition_config": {
      "type": "price",
      "symbol": "NIFTY50",
      "operator": "gt",
      "threshold": 24000
    },
    "notification_channels": ["telegram"]
  }'
```

### Using Python

```python
import httpx
import asyncio

async def create_alert():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8082/alerts",
            json={
                "name": "NIFTY 24000 breakout",
                "alert_type": "price",
                "priority": "high",
                "condition_config": {
                    "type": "price",
                    "symbol": "NIFTY50",
                    "operator": "gt",
                    "threshold": 24000
                },
                "notification_channels": ["telegram"]
            }
        )
        print(response.json())

asyncio.run(create_alert())
```

### Using the Test Script

```bash
# Edit test_alert_service.py and set your TELEGRAM_CHAT_ID
python test_alert_service.py
```

---

## API Endpoints Overview

### Alerts

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST   | `/alerts` | Create new alert |
| GET    | `/alerts` | List all alerts (with filters) |
| GET    | `/alerts/{alert_id}` | Get specific alert |
| PUT    | `/alerts/{alert_id}` | Update alert |
| DELETE | `/alerts/{alert_id}` | Delete alert (soft delete) |

### Alert Actions

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST   | `/alerts/{alert_id}/pause` | Pause alert evaluation |
| POST   | `/alerts/{alert_id}/resume` | Resume paused alert |
| POST   | `/alerts/{alert_id}/acknowledge` | Acknowledge alert event |
| POST   | `/alerts/{alert_id}/snooze` | Snooze alert for duration |
| POST   | `/alerts/{alert_id}/test` | Test alert (dry-run) |

### Statistics

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | `/alerts/stats/summary` | Get user alert statistics |

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | `/health` | Health check |
| GET    | `/metrics` | Prometheus metrics |
| GET    | `/` | Service info |

---

## Alert Types & Examples

### 1. Price Alert

Trigger when price crosses threshold:

```json
{
  "name": "NIFTY breakout above 24K",
  "alert_type": "price",
  "priority": "high",
  "condition_config": {
    "type": "price",
    "symbol": "NIFTY50",
    "operator": "gt",
    "threshold": 24000
  }
}
```

### 2. Position Alert (Stop Loss)

Trigger when position loss exceeds threshold:

```json
{
  "name": "Stop loss - P&L below -5000",
  "alert_type": "position",
  "priority": "critical",
  "condition_config": {
    "type": "position",
    "metric": "pnl",
    "operator": "lt",
    "threshold": -5000
  }
}
```

### 3. Indicator Alert

Trigger when technical indicator crosses threshold:

```json
{
  "name": "RSI overbought warning",
  "alert_type": "indicator",
  "priority": "medium",
  "condition_config": {
    "type": "indicator",
    "symbol": "NIFTY50",
    "indicator": "rsi",
    "timeframe": "5min",
    "operator": "gt",
    "threshold": 70,
    "lookback_periods": 14
  }
}
```

### 4. Composite Alert (Multiple Conditions)

Trigger when multiple conditions are met:

```json
{
  "name": "NIFTY overbought at resistance",
  "alert_type": "custom",
  "priority": "high",
  "condition_config": {
    "type": "composite",
    "operator": "and",
    "conditions": [
      {
        "type": "price",
        "symbol": "NIFTY50",
        "operator": "gt",
        "threshold": 24000
      },
      {
        "type": "indicator",
        "symbol": "NIFTY50",
        "indicator": "rsi",
        "operator": "gt",
        "threshold": 70
      }
    ]
  }
}
```

---

## Setting Up Telegram Notifications

### Step 1: Get Your Chat ID

1. Start a conversation with your bot: `@YourBotName`
2. Send any message to the bot
3. Visit: `https://api.telegram.org/bot8499559189:AAHjPsZHyCsI94k_H3pSJm1hg-d8rnisgSY/getUpdates`
4. Look for `"chat":{"id": YOUR_CHAT_ID}` in the response

### Step 2: Set Notification Preferences

```bash
curl -X PUT http://localhost:8082/notifications/preferences \
  -H "Content-Type: application/json" \
  -d '{
    "telegram_enabled": true,
    "telegram_chat_id": "YOUR_CHAT_ID",
    "max_notifications_per_hour": 50,
    "notification_format": "rich"
  }'
```

---

## Testing Checklist

Use this checklist to verify everything works:

- [ ] Service starts without errors
- [ ] Health check returns "ok"
- [ ] Can create alert via API
- [ ] Alert appears in database
- [ ] Can list alerts
- [ ] Can get specific alert by ID
- [ ] Can pause/resume alert
- [ ] Can delete alert
- [ ] Alert stats endpoint works
- [ ] Telegram notification setup (manual test)

---

## Troubleshooting

### Service won't start

**Error:** `Connection refused` or `Database connection failed`

**Solution:**
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Check database exists
psql -U stocksblitz -d stocksblitz_unified -c "SELECT 1"

# Verify .env file has correct credentials
cat .env | grep DB_
```

### Migrations fail

**Error:** `relation "alerts" already exists`

**Solution:**
```bash
# Drop tables if you need to start fresh (WARNING: destroys data)
psql -U stocksblitz -d stocksblitz_unified -c "
  DROP TABLE IF EXISTS notification_log CASCADE;
  DROP TABLE IF EXISTS alert_events CASCADE;
  DROP TABLE IF EXISTS notification_preferences CASCADE;
  DROP TABLE IF EXISTS alerts CASCADE;
"

# Re-run migrations
psql -U stocksblitz -d stocksblitz_unified -f migrations/001_create_alerts.sql
```

### Can't create alerts

**Error:** `422 Unprocessable Entity`

**Solution:**
- Check your JSON is valid
- Ensure all required fields are present
- Validate condition_config matches the alert_type
- Check logs: `tail -f /var/log/alert_service.log`

### Telegram notifications not working

**Checklist:**
- [ ] Bot token is correct in .env
- [ ] Chat ID is correct in preferences
- [ ] You've started a conversation with the bot
- [ ] Bot has not been blocked
- [ ] Check Telegram API: `curl https://api.telegram.org/bot{TOKEN}/getMe`

---

## Next Steps

### Phase 2: Add Evaluation Engine

1. Implement condition evaluator (`app/services/evaluator.py`)
2. Create background worker (`app/background/evaluation_worker.py`)
3. Add Redis integration for real-time state
4. Test alert triggering

### Phase 3: Integration

1. Update `docker-compose.yml` to include alert-service
2. Deploy to staging environment
3. Load testing
4. Python SDK updates

### Phase 4: Production

1. Add API key authentication
2. Implement rate limiting
3. Set up monitoring dashboards
4. Write deployment documentation

---

## Useful Commands

```bash
# Start service
uvicorn app.main:app --reload --port 8082

# Run tests
python test_alert_service.py

# Check logs (if using systemd)
journalctl -u alert-service -f

# View database tables
psql -U stocksblitz -d stocksblitz_unified -c "\dt"

# Count alerts
psql -U stocksblitz -d stocksblitz_unified -c "SELECT COUNT(*) FROM alerts"

# View recent alerts
psql -U stocksblitz -d stocksblitz_unified -c "
  SELECT alert_id, name, alert_type, status, created_at
  FROM alerts
  ORDER BY created_at DESC
  LIMIT 10;
"
```

---

## Support

- **API Documentation**: http://localhost:8082/docs
- **Design Document**: ../ALERT_SERVICE_DESIGN.md
- **Implementation Status**: ./IMPLEMENTATION_STATUS.md
- **Telegram Bot Token**: Check `.env` file

---

**Happy Alerting! 🔔**
