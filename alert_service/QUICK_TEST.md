# Alert Service - Quick Test Guide

Run these commands to test the alert service end-to-end.

## Prerequisites

```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/alert_service
```

## Step 1: Run Migrations (First Time Only)

```bash
PGPASSWORD=stocksblitz123 psql -U stocksblitz -d stocksblitz_unified -f migrations/000_verify_timescaledb.sql
PGPASSWORD=stocksblitz123 psql -U stocksblitz -d stocksblitz_unified -f migrations/001_create_alerts.sql
PGPASSWORD=stocksblitz123 psql -U stocksblitz -d stocksblitz_unified -f migrations/002_create_alert_events.sql
PGPASSWORD=stocksblitz123 psql -U stocksblitz -d stocksblitz_unified -f migrations/003_create_notification_preferences.sql
```

## Step 2: Install Dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Step 3: Start the Service

```bash
uvicorn app.main:app --reload --port 8082
```

Expected output:
```
INFO: Evaluation worker started
INFO: alert-service started successfully on port 8082
INFO: Uvicorn running on http://127.0.0.1:8082
```

## Step 4: Test Basic Functionality

### Health Check

```bash
curl http://localhost:8082/health | jq
```

### Create a Price Alert

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
    "evaluation_interval_seconds": 30
  }' | jq
```

Save the `alert_id` from the response.

### Test Manual Evaluation

```bash
# Replace ALERT_ID with the ID from above
ALERT_ID="your-alert-id-here"

curl -X POST "http://localhost:8082/alerts/$ALERT_ID/test" | jq
```

This will show:
- ✅ Whether condition is currently met
- Current market price
- Threshold value
- Any errors

### List All Alerts

```bash
curl http://localhost:8082/alerts | jq
```

### Check Alert Statistics

```bash
curl http://localhost:8082/alerts/stats/summary | jq
```

## Step 5: Test Background Worker

The background worker evaluates alerts automatically every 10-30 seconds.

### Watch for Evaluations

```bash
# Get alert details (repeat this every 10 seconds)
curl http://localhost:8082/alerts/$ALERT_ID | jq '.last_evaluated_at, .trigger_count'
```

You should see:
- `last_evaluated_at` updating automatically
- `trigger_count` incrementing if condition is met

### Check Service Logs

In the terminal where uvicorn is running, watch for:

```
INFO: Evaluation cycle complete: X alerts evaluated in Y.YYs
INFO: Alert {id} condition matched!
INFO: Alert {id} triggered successfully
```

## Step 6: Run Comprehensive Tests

```bash
# In a new terminal (keep uvicorn running)
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/alert_service
source venv/bin/activate
python test_evaluation.py
```

This runs:
1. Health check
2. Price alert creation
3. Manual evaluation
4. Background worker test
5. Indicator alert test
6. Composite alert test

## Step 7: Check Telegram Notifications

If an alert triggers:
1. Check your Telegram for messages
2. Should see alert notification with:
   - Alert name
   - Symbol and current price
   - Threshold
   - Timestamp
   - Interactive buttons (acknowledge, snooze, pause)

## Common Issues

### Service won't start

**Error**: `Database connection failed`

**Fix**:
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Check database exists
PGPASSWORD=stocksblitz123 psql -U stocksblitz -d stocksblitz_unified -c "SELECT 1"
```

### Evaluation not working

**Check**: Is ticker_service running?
```bash
curl http://localhost:8080/health
```

If not, start it:
```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/ticker_service
docker-compose up -d
```

### No Telegram notifications

**Check**: Telegram token in .env
```bash
cat .env | grep TELEGRAM_BOT_TOKEN
```

**Check**: Notification preferences set
```bash
curl http://localhost:8082/notifications/preferences | jq
```

## Quick Commands Reference

```bash
# Start service
uvicorn app.main:app --reload --port 8082

# Create alert
curl -X POST http://localhost:8082/alerts -H "Content-Type: application/json" -d '{...}'

# List alerts
curl http://localhost:8082/alerts | jq

# Get alert
curl http://localhost:8082/alerts/{alert_id} | jq

# Test alert
curl -X POST http://localhost:8082/alerts/{alert_id}/test | jq

# Pause alert
curl -X POST http://localhost:8082/alerts/{alert_id}/pause | jq

# Resume alert
curl -X POST http://localhost:8082/alerts/{alert_id}/resume | jq

# Delete alert
curl -X DELETE http://localhost:8082/alerts/{alert_id} | jq

# Get stats
curl http://localhost:8082/alerts/stats/summary | jq

# Health check
curl http://localhost:8082/health | jq

# API docs (browser)
open http://localhost:8082/docs
```

## Test Scenarios

### Scenario 1: Price Alert (Should Trigger)

Create alert with current price threshold:

```bash
# First, get current NIFTY price
curl http://localhost:8080/live/NIFTY50 | jq '.last_price'

# Create alert with threshold BELOW current price
curl -X POST http://localhost:8082/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test - Should Trigger",
    "alert_type": "price",
    "priority": "critical",
    "condition_config": {
      "type": "price",
      "symbol": "NIFTY50",
      "operator": "gt",
      "threshold": 20000
    },
    "evaluation_interval_seconds": 20,
    "cooldown_seconds": 60
  }' | jq
```

Expected: Alert triggers within 30 seconds, Telegram notification received.

### Scenario 2: Price Alert (Should NOT Trigger)

```bash
curl -X POST http://localhost:8082/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test - Should NOT Trigger",
    "alert_type": "price",
    "priority": "medium",
    "condition_config": {
      "type": "price",
      "symbol": "NIFTY50",
      "operator": "gt",
      "threshold": 50000
    },
    "evaluation_interval_seconds": 20
  }' | jq
```

Expected: Alert evaluates but does NOT trigger.

### Scenario 3: Cooldown Test

```bash
# Create alert with short cooldown
curl -X POST http://localhost:8082/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Cooldown Test",
    "alert_type": "price",
    "priority": "high",
    "condition_config": {
      "type": "price",
      "symbol": "NIFTY50",
      "operator": "gt",
      "threshold": 20000
    },
    "evaluation_interval_seconds": 10,
    "cooldown_seconds": 300
  }' | jq
```

Expected:
1. First trigger succeeds
2. Subsequent evaluations skip trigger due to cooldown
3. Check logs for "cooldown active" message

### Scenario 4: Daily Limit Test

```bash
curl -X POST http://localhost:8082/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Daily Limit Test",
    "alert_type": "price",
    "priority": "high",
    "condition_config": {
      "type": "price",
      "symbol": "NIFTY50",
      "operator": "gt",
      "threshold": 20000
    },
    "evaluation_interval_seconds": 10,
    "cooldown_seconds": 10,
    "max_triggers_per_day": 3
  }' | jq
```

Expected:
1. Triggers 3 times (check trigger_count)
2. Fourth trigger skipped: "daily limit reached"

## Success Indicators

✅ Service starts without errors
✅ Health check returns "ok"
✅ Alerts can be created
✅ Manual test endpoint works
✅ Background worker logs show evaluation cycles
✅ last_evaluated_at updates automatically
✅ Alerts trigger when condition met
✅ trigger_count increments
✅ Telegram notifications received
✅ alert_events records created
✅ Cooldown prevents spam
✅ Daily limits enforced

## API Documentation

Full interactive API docs: http://localhost:8082/docs

## Need Help?

1. Check logs in uvicorn terminal
2. Check health: `curl http://localhost:8082/health`
3. Check DATABASE_SCHEMA_REFERENCE.md
4. Check PHASE2_COMPLETE.md
5. Check GETTING_STARTED.md

---

**Quick Test Time**: ~5 minutes
**Full Test Time**: ~15 minutes
**Recommended**: Run test_evaluation.py for comprehensive testing
