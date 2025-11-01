# Alert Service - Quick Start Guide

## TL;DR

A production-ready alert service for StocksBlitz that provides real-time trading alerts via Telegram (initially) and mobile apps (future). Designed as a standalone microservice with PostgreSQL + TimescaleDB for persistence and Redis for real-time state.

---

## Key Design Decisions

### 1. Standalone Microservice (Recommended)
- **Why?** Independent scaling, isolation, and multi-tenancy ready
- **Port:** 8082
- **Communication:** REST API + WebSocket
- **Database:** Shared PostgreSQL with backend (stocksblitz_unified)

### 2. Technology Stack
```
FastAPI (Python 3.11+)
PostgreSQL + TimescaleDB (time-series alerts)
Redis (active state + pub/sub)
Telegram Bot API (notifications)
Prometheus (metrics)
```

### 3. Core Components

```
alert_service/
├── app/
│   ├── services/
│   │   ├── alert_service.py        # CRUD operations
│   │   ├── evaluator.py            # Condition evaluation
│   │   └── notification_service.py # Telegram/FCM/Email
│   ├── background/
│   │   └── evaluation_worker.py    # Continuous alert evaluation
│   └── routes/
│       └── alerts.py               # REST API
├── migrations/
│   └── 001_create_alerts.sql       # Database schema
└── Dockerfile
```

---

## Database Schema (Core Tables)

### 1. `alerts` - Alert definitions
```sql
CREATE TABLE alerts (
    alert_id UUID PRIMARY KEY,
    user_id VARCHAR(100),
    alert_type VARCHAR(50),          -- price, position, indicator, etc.
    priority VARCHAR(20),             -- low, medium, high, critical
    condition_config JSONB,           -- Flexible condition definition
    notification_channels TEXT[],     -- ['telegram', 'fcm', 'email']
    status VARCHAR(20),               -- active, paused, triggered
    evaluation_interval_seconds INT,
    cooldown_seconds INT,
    ...
);
```

### 2. `alert_events` - Trigger history (TimescaleDB)
```sql
CREATE TABLE alert_events (
    event_id UUID PRIMARY KEY,
    alert_id UUID REFERENCES alerts,
    triggered_at TIMESTAMPTZ,
    status VARCHAR(20),               -- triggered, acknowledged, snoozed
    trigger_value JSONB,
    notification_sent BOOLEAN,
    ...
);
```

---

## Alert Types & Examples

### 1. Price Alert
```json
{
  "alert_type": "price",
  "condition_config": {
    "type": "price",
    "symbol": "NIFTY50",
    "operator": "gt",
    "threshold": 24000
  }
}
```

### 2. Position Alert (Stop Loss)
```json
{
  "alert_type": "position",
  "condition_config": {
    "type": "position",
    "metric": "pnl",
    "operator": "lt",
    "threshold": -5000
  }
}
```

### 3. Indicator Alert
```json
{
  "alert_type": "indicator",
  "condition_config": {
    "type": "indicator",
    "indicator": "rsi",
    "operator": "gt",
    "threshold": 70
  }
}
```

### 4. Composite Alert (Multiple Conditions)
```json
{
  "alert_type": "custom",
  "condition_config": {
    "type": "composite",
    "operator": "and",
    "conditions": [
      {"type": "price", "operator": "gt", "threshold": 24000},
      {"type": "indicator", "indicator": "rsi", "operator": "gt", "threshold": 70}
    ]
  }
}
```

---

## API Endpoints (Quick Reference)

### Alert Management
```bash
# Create alert
POST /alerts
Body: {name, alert_type, condition_config, notification_channels}

# List alerts
GET /alerts?status=active&alert_type=price

# Get alert
GET /alerts/{alert_id}

# Update alert
PUT /alerts/{alert_id}

# Delete alert
DELETE /alerts/{alert_id}
```

### Alert Actions
```bash
# Pause/Resume
POST /alerts/{alert_id}/pause
POST /alerts/{alert_id}/resume

# Acknowledge
POST /alerts/{alert_id}/acknowledge

# Snooze
POST /alerts/{alert_id}/snooze
Body: {duration_seconds: 3600}

# Test (dry-run)
POST /alerts/{alert_id}/test
```

### Notifications
```bash
# Get preferences
GET /notifications/preferences

# Update preferences
PUT /notifications/preferences
Body: {telegram_enabled, telegram_chat_id, quiet_hours_start, ...}

# Setup Telegram
POST /notifications/telegram/setup
```

### WebSocket
```bash
# Real-time alert events
WS /alerts/stream?api_key={api_key}
```

---

## Python SDK Usage

### Installation
```bash
pip install stocksblitz-sdk  # (when published)
```

### Basic Usage
```python
from stocksblitz_sdk import TradingClient

# Initialize client
client = TradingClient(
    api_url="http://localhost:8082",
    api_key="sb_xxx_yyy"
)

# Create price alert
alert_id = client.alerts.create_price_alert(
    symbol="NIFTY50",
    operator="gt",
    threshold=24000,
    priority="high"
)

# Create position stop loss
alert_id = client.alerts.create_position_alert(
    metric="pnl",
    operator="lt",
    threshold=-5000,
    priority="critical"
)

# List alerts
alerts = client.alerts.list_alerts(status="active")

# Delete alert
client.alerts.delete_alert(alert_id)
```

### Real-Time Streaming
```python
import asyncio

async def on_alert(event):
    print(f"🔔 {event['name']}")
    if event['priority'] == 'critical':
        client.alerts.acknowledge(event['alert_id'], event['event_id'])

# Stream events
asyncio.run(client.alerts.stream_events(on_alert))
```

---

## Evaluation Engine

### How It Works

1. **Background Worker** runs continuously
2. Fetches alerts due for evaluation based on `evaluation_interval_seconds`
3. **Priority-based batching**:
   - Critical: Every 10-30 seconds
   - High: Every 1 minute
   - Medium: Every 5 minutes
   - Low: Every 15 minutes
4. Evaluates conditions against live data
5. Triggers notifications if condition met
6. Respects **cooldown** periods (prevents spam)

### Smart Optimization
- **Symbol-based batching**: Fetch market data once per symbol
- **Redis pub/sub**: Real-time price triggers
- **Circuit breakers**: Graceful degradation on external API failures
- **Caching**: Redis cache for market data (5-second TTL)

---

## Notification Flow

```
Alert Triggered
    ↓
Create alert_event record
    ↓
Format message (priority-based template)
    ↓
Check user preferences (quiet hours, rate limits)
    ↓
Send via channel (Telegram)
    ↓
Log notification_log entry
    ↓
Update alert state (trigger_count, last_triggered_at)
```

### Telegram Message Format
```
🔔 Price Alert: NIFTY50

Current: ₹24,150 (+0.62%)
Trigger: Price > ₹24,000

Time: 2025-11-01 14:35:20 IST
Alert: "NIFTY breakout above 24K"

[View Chart] [Acknowledge] [Snooze]
```

---

## User Service Integration (Future-Proof)

### Current (Phase 1)
- User identification via API key (`api_keys.user_id`)
- Notification preferences in alert_service's own table
- Single tenant per API key

### Future (Phase 2 - with user_service)
- User service becomes source of truth for user data
- Alert service caches user preferences in Redis
- Graceful degradation if user_service unavailable
- Circuit breaker pattern for resilience

**Migration Path:**
1. Keep alert_service's `notification_preferences` table
2. Add sync mechanism when user_service launches
3. Implement fallback to local preferences
4. No breaking changes to existing alerts

---

## Docker Deployment

### docker-compose.yml
```yaml
services:
  alert-service:
    build: ./alert_service
    ports:
      - "127.0.0.1:8082:8082"
    environment:
      - DB_HOST=host.docker.internal
      - REDIS_URL=redis://redis:6379/1
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - BACKEND_URL=http://backend:8000
      - TICKER_SERVICE_URL=http://ticker-service:8080
    depends_on:
      - redis
      - backend
    networks:
      - tv-network
```

### Environment Variables (.env)
```bash
DB_HOST=localhost
DB_NAME=stocksblitz_unified
REDIS_URL=redis://localhost:6379/1
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHI...
BACKEND_URL=http://localhost:8000
TICKER_SERVICE_URL=http://localhost:8080
```

---

## Security & Rate Limiting

### Authentication
- Reuses backend's API key system
- Validates against shared `api_keys` table
- Permissions: `can_read`, `can_create_alerts`, `can_manage_alerts`

### Rate Limits
**Per-User:**
- 100 alert creations/hour
- 50 notifications/hour (configurable)

**Global:**
- Telegram: 30 messages/second (Bot API limit)

**Implementation:**
```python
# Redis token bucket
await rate_limiter.check_limit(user_id, limit=100, window=3600)
```

---

## Monitoring & Observability

### Prometheus Metrics (Port 9092)
```
alerts_created_total{alert_type, priority}
alerts_triggered_total{alert_type, priority}
notifications_sent_total{channel, status}
evaluation_duration_seconds{alert_type}
active_alerts_total{alert_type, priority}
evaluation_queue_size
```

### Health Check
```bash
curl http://localhost:8082/health

{
  "status": "ok",
  "database": "healthy",
  "redis": "healthy",
  "telegram": "healthy"
}
```

### Structured Logging
```json
{
  "timestamp": "2025-11-01T14:35:20Z",
  "level": "INFO",
  "message": "Alert triggered",
  "alert_id": "550e8400-...",
  "user_id": "user_123",
  "alert_type": "price",
  "trigger_value": 24150
}
```

---

## Implementation Roadmap (10 Weeks)

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| **Phase 1: Core Infrastructure** | Week 1-2 | Database schema, CRUD API, Authentication |
| **Phase 2: Evaluation Engine** | Week 3-4 | Condition evaluators, Background worker |
| **Phase 3: Notification System** | Week 5-6 | Telegram integration, Rate limiting |
| **Phase 4: SDK & Testing** | Week 7-8 | Python SDK, Load testing, Security audit |
| **Phase 5: Advanced Features** | Week 9-10 | Greeks, Custom scripts, Analytics, UI |

---

## Next Steps

1. **Review this design document** with the team
2. **Decide on deployment strategy** (standalone vs integrated)
3. **Set up Telegram bot** (if approved)
4. **Create initial migrations** and test database schema
5. **Start Phase 1 implementation** (Core Infrastructure)

---

## Key Files

- `ALERT_SERVICE_DESIGN.md` - Full detailed design (this document)
- `alert_service/` - Service implementation folder (to be created)
- `backend/migrations/014_create_alerts.sql` - Database migration
- `python-sdk/stocksblitz_sdk/services/alerts_v2.py` - SDK integration

---

## Questions & Considerations

1. **Standalone vs Integrated?**
   - Recommendation: Standalone microservice
   - Pros: Independent scaling, isolation, future-proof
   - Cons: Slightly more complex deployment

2. **Telegram Bot Setup**
   - Need to create bot via @BotFather
   - Store bot token securely (env variable)
   - Set up webhook for interactive buttons

3. **User Service Timeline**
   - When will user_service be added?
   - Current design allows seamless migration
   - No breaking changes needed

4. **Notification Channels Priority**
   - Start with Telegram (easiest to implement)
   - Add FCM/APNS when mobile app ready
   - Email/SMS later (optional)

5. **Cost Considerations**
   - Telegram: Free (with rate limits)
   - FCM: Free up to 1M messages/day
   - SMS: Paid (consider later)

---

## Support & Documentation

- Full API docs: `http://localhost:8082/docs` (auto-generated)
- Metrics dashboard: `http://localhost:9092/metrics`
- Health check: `http://localhost:8082/health`

For questions or feedback, contact the StocksBlitz engineering team.

---

**Version:** 1.0
**Last Updated:** 2025-11-01
**Status:** Design Review
