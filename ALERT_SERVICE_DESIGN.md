# Alert Service - Comprehensive Design Document

## Executive Summary

This document outlines the design for a production-ready Alert Service for the StocksBlitz trading platform. The service will provide real-time alerting capabilities for market events, position changes, and custom conditions, starting with Telegram notifications and extensible to mobile apps and other channels.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Database Schema](#2-database-schema)
3. [Alert Types & Conditions](#3-alert-types--conditions)
4. [Notification System](#4-notification-system)
5. [API Design](#5-api-design)
6. [Evaluation Engine](#6-evaluation-engine)
7. [User Service Integration](#7-user-service-integration)
8. [Python SDK Integration](#8-python-sdk-integration)
9. [Configuration & Deployment](#9-configuration--deployment)
10. [Security & Rate Limiting](#10-security--rate-limiting)
11. [Monitoring & Observability](#11-monitoring--observability)
12. [Implementation Roadmap](#12-implementation-roadmap)

---

## 1. Architecture Overview

### 1.1 Deployment Strategy

**Recommended: Standalone Microservice** (`alert_service/`)

**Rationale:**
- **Independent scaling**: Alert evaluation and notification delivery have different resource profiles than trading operations
- **Isolation**: Service failures don't impact core trading functionality
- **Multi-tenancy ready**: Easy to scale per-user when user_service is added
- **Clear boundaries**: Aligns with existing microservices pattern (ticker_service, calendar_service)

**Service Communication:**
```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│  Backend API    │◄────►│  Alert Service   │◄────►│  Ticker Service │
│  (Port 8000)    │      │  (Port 8082)     │      │  (Port 8080)    │
└────────┬────────┘      └────────┬─────────┘      └─────────────────┘
         │                        │                           │
         ├────────────────────────┼───────────────────────────┤
         │                        │                           │
    ┌────▼────────────────────────▼───────────────────────────▼────┐
    │             PostgreSQL + TimescaleDB + Redis                 │
    └──────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
                        ┌──────────────────────┐
                        │  Telegram Bot API    │
                        │  (Future: FCM, APNS) │
                        └──────────────────────┘
```

### 1.2 Technology Stack

- **Runtime**: Python 3.11+ with FastAPI (async/await)
- **Database**: PostgreSQL (shared) with TimescaleDB for alert history
- **Cache**: Redis for active alert state, rate limiting, and pub/sub
- **Monitoring**: Prometheus + structured logging
- **Notifications**:
  - Telegram Bot API (initial)
  - Firebase Cloud Messaging (mobile - future)
  - Apple Push Notification Service (iOS - future)
  - Email/SMS (future)

### 1.3 File Structure

```
alert_service/
├── app/
│   ├── main.py                      # FastAPI application entry
│   ├── config.py                    # Pydantic settings
│   ├── database.py                  # Database connection pool
│   ├── models/
│   │   ├── alert.py                 # Alert Pydantic models
│   │   ├── notification.py          # Notification models
│   │   └── condition.py             # Condition models
│   ├── routes/
│   │   ├── alerts.py                # CRUD API endpoints
│   │   ├── notifications.py         # Notification management
│   │   └── webhooks.py              # Webhook callbacks
│   ├── services/
│   │   ├── alert_service.py         # Core alert management
│   │   ├── evaluator.py             # Condition evaluation engine
│   │   ├── notification_service.py  # Notification dispatch
│   │   └── providers/
│   │       ├── base.py              # Abstract notification provider
│   │       ├── telegram.py          # Telegram implementation
│   │       ├── fcm.py               # Firebase (future)
│   │       └── email.py             # Email (future)
│   ├── background/
│   │   ├── evaluation_worker.py     # Alert evaluation loop
│   │   └── cleanup_worker.py        # Expired alert cleanup
│   └── auth.py                      # API key authentication
├── migrations/
│   ├── 001_create_alerts.sql
│   ├── 002_create_notifications.sql
│   └── 003_create_user_preferences.sql
├── tests/
│   ├── unit/
│   ├── integration/
│   └── load/
├── Dockerfile
├── docker-compose.yml               # Local testing
├── requirements.txt
├── .env.example
└── README.md
```

---

## 2. Database Schema

### 2.1 Core Tables

#### `alerts` - Main alert definitions

```sql
CREATE TABLE alerts (
    alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Ownership (future-proof for user_service)
    user_id VARCHAR(100) NOT NULL,                    -- User identifier (from API key or future user_service)
    account_id VARCHAR(100),                          -- Optional: specific trading account
    strategy_id UUID,                                 -- Optional: link to strategy

    -- Alert metadata
    name VARCHAR(255) NOT NULL,
    description TEXT,
    alert_type VARCHAR(50) NOT NULL,                  -- price, indicator, position, greek, order, time, custom
    priority VARCHAR(20) NOT NULL DEFAULT 'medium',   -- low, medium, high, critical

    -- Condition specification
    condition_type VARCHAR(50) NOT NULL,              -- simple, composite, script
    condition_config JSONB NOT NULL,                  -- Flexible condition definition

    -- Scope
    symbol VARCHAR(50),                               -- Optional: specific instrument
    symbols TEXT[],                                   -- Optional: multiple instruments
    exchange VARCHAR(10),                             -- NSE, NFO, BSE, etc.

    -- Notification configuration
    notification_channels TEXT[] NOT NULL DEFAULT ARRAY['telegram'],
    notification_config JSONB,                        -- Channel-specific config
    notification_template TEXT,                       -- Custom message template

    -- State
    status VARCHAR(20) NOT NULL DEFAULT 'active',     -- active, paused, triggered, expired, deleted

    -- Evaluation settings
    evaluation_interval_seconds INT DEFAULT 60,       -- How often to evaluate (min: 10s)
    evaluation_window_start TIME,                     -- Optional: only evaluate during time window
    evaluation_window_end TIME,
    max_triggers_per_day INT,                         -- Optional: daily trigger limit
    cooldown_seconds INT DEFAULT 300,                 -- Cooldown between triggers (5 min default)

    -- Trigger tracking
    trigger_count INT DEFAULT 0,
    last_triggered_at TIMESTAMPTZ,
    last_evaluated_at TIMESTAMPTZ,
    evaluation_count BIGINT DEFAULT 0,

    -- Lifecycle
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,                           -- Optional: auto-disable after date
    created_by VARCHAR(100),                          -- API key or user

    -- Audit
    metadata JSONB,                                   -- Extensibility for custom fields

    CONSTRAINT valid_priority CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    CONSTRAINT valid_status CHECK (status IN ('active', 'paused', 'triggered', 'expired', 'deleted')),
    CONSTRAINT valid_alert_type CHECK (alert_type IN ('price', 'indicator', 'position', 'greek', 'order', 'time', 'custom', 'strategy')),
    CONSTRAINT valid_evaluation_interval CHECK (evaluation_interval_seconds >= 10)
);

-- Indexes
CREATE INDEX idx_alerts_user_id ON alerts(user_id, status) WHERE status = 'active';
CREATE INDEX idx_alerts_status ON alerts(status) WHERE status = 'active';
CREATE INDEX idx_alerts_symbol ON alerts(symbol) WHERE symbol IS NOT NULL AND status = 'active';
CREATE INDEX idx_alerts_next_eval ON alerts(last_evaluated_at) WHERE status = 'active';
CREATE INDEX idx_alerts_expires_at ON alerts(expires_at) WHERE expires_at IS NOT NULL;
CREATE INDEX idx_alerts_condition_type ON alerts(alert_type, condition_type);

-- GIN index for JSONB condition queries
CREATE INDEX idx_alerts_condition_config ON alerts USING GIN (condition_config);

-- Comments
COMMENT ON TABLE alerts IS 'User-defined alerts for market events and trading conditions';
COMMENT ON COLUMN alerts.condition_config IS 'JSONB structure depends on condition_type. See condition schemas.';
COMMENT ON COLUMN alerts.evaluation_interval_seconds IS 'Minimum 10 seconds. Lower values increase load.';
COMMENT ON COLUMN alerts.cooldown_seconds IS 'Prevents alert spam. Minimum time between consecutive triggers.';
```

#### `alert_events` - Alert trigger history (TimescaleDB hypertable)

```sql
CREATE TABLE alert_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id UUID NOT NULL REFERENCES alerts(alert_id) ON DELETE CASCADE,

    -- Event details
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status VARCHAR(20) NOT NULL,                      -- triggered, acknowledged, snoozed, resolved

    -- Trigger context
    trigger_value JSONB,                              -- Actual values that triggered alert
    evaluation_result JSONB,                          -- Full evaluation context

    -- Notification tracking
    notification_sent BOOLEAN DEFAULT false,
    notification_channels TEXT[],
    notification_ids JSONB,                           -- Channel-specific message IDs

    -- User actions
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by VARCHAR(100),
    snoozed_until TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,

    -- Metadata
    metadata JSONB,

    CONSTRAINT valid_event_status CHECK (status IN ('triggered', 'acknowledged', 'snoozed', 'resolved'))
);

-- Convert to hypertable (time-series optimization)
SELECT create_hypertable('alert_events', 'triggered_at', if_not_exists => TRUE, chunk_time_interval => INTERVAL '7 days');

-- Indexes
CREATE INDEX idx_alert_events_alert_id ON alert_events(alert_id, triggered_at DESC);
CREATE INDEX idx_alert_events_status ON alert_events(status, triggered_at DESC);
CREATE INDEX idx_alert_events_user ON alert_events(
    (SELECT user_id FROM alerts WHERE alerts.alert_id = alert_events.alert_id),
    triggered_at DESC
);

-- Retention policy: Keep events for 6 months
SELECT add_retention_policy('alert_events', INTERVAL '180 days', if_not_exists => TRUE);
```

#### `notification_preferences` - User notification settings (future)

```sql
CREATE TABLE notification_preferences (
    user_id VARCHAR(100) PRIMARY KEY,

    -- Channel configurations
    telegram_enabled BOOLEAN DEFAULT false,
    telegram_chat_id VARCHAR(100),
    telegram_bot_token VARCHAR(255),

    fcm_enabled BOOLEAN DEFAULT false,
    fcm_device_tokens TEXT[],

    email_enabled BOOLEAN DEFAULT false,
    email_addresses TEXT[],

    -- Global settings
    quiet_hours_start TIME,                           -- Do not disturb window
    quiet_hours_end TIME,
    quiet_hours_timezone VARCHAR(50) DEFAULT 'Asia/Kolkata',

    max_notifications_per_hour INT DEFAULT 50,        -- Rate limiting per user
    priority_threshold VARCHAR(20) DEFAULT 'low',     -- Only send >= this priority during quiet hours

    -- Preferences
    notification_format VARCHAR(20) DEFAULT 'rich',   -- rich, compact, minimal
    include_chart_images BOOLEAN DEFAULT false,       -- Attach chart screenshots

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    metadata JSONB
);

-- Indexes
CREATE INDEX idx_notif_prefs_telegram ON notification_preferences(telegram_chat_id) WHERE telegram_enabled = true;
```

#### `notification_log` - Delivery tracking (TimescaleDB hypertable)

```sql
CREATE TABLE notification_log (
    log_id UUID DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES alert_events(event_id) ON DELETE CASCADE,

    -- Notification details
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    channel VARCHAR(50) NOT NULL,                     -- telegram, fcm, email, webhook
    recipient VARCHAR(255) NOT NULL,                  -- chat_id, device_token, email

    -- Delivery status
    status VARCHAR(20) NOT NULL,                      -- pending, sent, delivered, failed, read
    status_code INT,
    error_message TEXT,

    -- Content
    message_id VARCHAR(255),                          -- Provider-specific message ID
    message_content TEXT,
    message_metadata JSONB,

    -- Tracking
    delivered_at TIMESTAMPTZ,
    read_at TIMESTAMPTZ,
    clicked BOOLEAN DEFAULT false,

    PRIMARY KEY (log_id, sent_at),                    -- Composite key for hypertable

    CONSTRAINT valid_channel CHECK (channel IN ('telegram', 'fcm', 'apns', 'email', 'sms', 'webhook')),
    CONSTRAINT valid_status CHECK (status IN ('pending', 'sent', 'delivered', 'failed', 'read'))
);

-- Convert to hypertable
SELECT create_hypertable('notification_log', 'sent_at', if_not_exists => TRUE, chunk_time_interval => INTERVAL '7 days');

-- Indexes
CREATE INDEX idx_notif_log_event_id ON notification_log(event_id, sent_at DESC);
CREATE INDEX idx_notif_log_status ON notification_log(status, sent_at DESC) WHERE status IN ('pending', 'failed');
CREATE INDEX idx_notif_log_channel ON notification_log(channel, sent_at DESC);

-- Retention policy: Keep logs for 90 days
SELECT add_retention_policy('notification_log', INTERVAL '90 days', if_not_exists => TRUE);
```

### 2.2 Condition Configuration Schemas

The `condition_config` JSONB field supports various schemas based on `condition_type`:

#### Price Condition
```json
{
  "type": "price",
  "operator": "gt",           // gt, gte, lt, lte, eq, between
  "threshold": 24000,
  "comparison": "last_price", // last_price, bid, ask, vwap
  "symbol": "NIFTY50"
}
```

#### Indicator Condition
```json
{
  "type": "indicator",
  "indicator": "rsi",
  "timeframe": "5min",
  "operator": "gt",
  "threshold": 70,
  "lookback_periods": 14
}
```

#### Position Condition
```json
{
  "type": "position",
  "metric": "pnl",            // pnl, day_pnl, quantity, pnl_percentage
  "operator": "lt",
  "threshold": -5000,
  "symbol": "NIFTYOCT24FUT"   // Optional: specific position
}
```

#### Greek Condition (Options)
```json
{
  "type": "greek",
  "greek": "delta",           // delta, gamma, theta, vega
  "operator": "between",
  "min": 0.4,
  "max": 0.6,
  "position_type": "long_call"
}
```

#### Composite Condition (AND/OR logic)
```json
{
  "type": "composite",
  "operator": "and",          // and, or
  "conditions": [
    {
      "type": "price",
      "operator": "gt",
      "threshold": 24000
    },
    {
      "type": "indicator",
      "indicator": "rsi",
      "operator": "lt",
      "threshold": 30
    }
  ]
}
```

#### Time Condition
```json
{
  "type": "time",
  "schedule": "cron",
  "expression": "0 9 * * 1-5", // Every weekday at 9 AM
  "timezone": "Asia/Kolkata",
  "message": "Market opening reminder"
}
```

#### Custom Script Condition (Advanced)
```json
{
  "type": "script",
  "language": "python",
  "script": "return current_price > sma_20 and volume > avg_volume * 1.5",
  "timeout_seconds": 5
}
```

---

## 3. Alert Types & Conditions

### 3.1 Supported Alert Types

| Alert Type | Description | Example Use Cases |
|------------|-------------|-------------------|
| `price` | Price crosses threshold | NIFTY > 24000, BANKNIFTY < 45000 |
| `indicator` | Technical indicator condition | RSI > 70, MACD crossover |
| `position` | Position-based alerts | P&L < -5000, Position size > 100 lots |
| `greek` | Option greeks monitoring | Delta approaching 0.5, Theta decay alert |
| `order` | Order status changes | Order filled, Order rejected |
| `time` | Time-based reminders | Market open, Expiry day reminder |
| `strategy` | Strategy performance | Strategy drawdown > 10%, Daily target hit |
| `custom` | Custom logic via script | Complex multi-condition checks |

### 3.2 Evaluation Strategy

**Priority-Based Evaluation:**
1. **Critical** alerts: Evaluate every 10-30 seconds
2. **High** alerts: Evaluate every 1 minute
3. **Medium** alerts: Evaluate every 5 minutes
4. **Low** alerts: Evaluate every 15 minutes

**Smart Batching:**
- Group alerts by symbol to batch data fetches
- Use Redis pub/sub for real-time price triggers
- Implement circuit breakers for external API failures

---

## 4. Notification System

### 4.1 Architecture

```python
# Provider abstraction
class NotificationProvider(ABC):
    @abstractmethod
    async def send(
        self,
        recipient: str,
        message: str,
        priority: str,
        metadata: Dict[str, Any]
    ) -> NotificationResult:
        """Send notification via this channel."""
        pass

    @abstractmethod
    async def validate_recipient(self, recipient: str) -> bool:
        """Validate recipient identifier."""
        pass

    @abstractmethod
    async def get_status(self, message_id: str) -> str:
        """Get delivery status of sent message."""
        pass
```

### 4.2 Telegram Implementation

```python
class TelegramProvider(NotificationProvider):
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.client = httpx.AsyncClient(
            base_url="https://api.telegram.org",
            timeout=10.0
        )

    async def send(
        self,
        recipient: str,  # chat_id
        message: str,
        priority: str,
        metadata: Dict[str, Any]
    ) -> NotificationResult:
        """Send message via Telegram Bot API."""

        # Format message with priority indicator
        emoji = {"critical": "🚨", "high": "⚠️", "medium": "ℹ️", "low": "📢"}
        formatted_msg = f"{emoji.get(priority, '')} {message}"

        # Build request
        url = f"/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": recipient,
            "text": formatted_msg,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }

        # Add action buttons for critical alerts
        if priority == "critical":
            payload["reply_markup"] = {
                "inline_keyboard": [[
                    {"text": "✅ Acknowledge", "callback_data": f"ack:{metadata['event_id']}"},
                    {"text": "💤 Snooze 1h", "callback_data": f"snooze:{metadata['event_id']}:3600"}
                ]]
            }

        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()

            return NotificationResult(
                success=True,
                message_id=str(result["result"]["message_id"]),
                provider_response=result
            )
        except httpx.HTTPError as e:
            logger.error(f"Telegram send failed: {e}")
            return NotificationResult(
                success=False,
                error_message=str(e)
            )
```

### 4.3 Message Templates

**Price Alert Template:**
```
🔔 Price Alert: NIFTY50

Current: ₹24,150 (+0.62%)
Trigger: Price > ₹24,000

Time: 2025-11-01 14:35:20 IST
Alert: "NIFTY breakout above 24K"

[View Chart] [Acknowledge] [Snooze]
```

**Position Alert Template:**
```
⚠️ Position Alert: NIFTYOCT24FUT

P&L: -₹5,250 (-2.15%)
Day P&L: -₹1,800
Quantity: 100 lots
Avg Price: ₹24,050
Current: ₹23,998

Alert: "Position loss > ₹5,000"

[Close Position] [Acknowledge]
```

### 4.4 Rate Limiting

**Per-User Rate Limits:**
- Default: 50 notifications/hour
- Critical alerts: Exempt from rate limiting
- Cooldown: 5 minutes between same alert triggers

**Global Rate Limits:**
- Telegram: 30 messages/second (Bot API limit)
- Use token bucket algorithm via Redis
- Queue excess notifications for batch delivery

---

## 5. API Design

### 5.1 REST Endpoints

#### Alert Management

```python
# Create alert
POST /alerts
Authorization: Bearer {api_key}
Content-Type: application/json

{
  "name": "NIFTY 24000 breakout",
  "alert_type": "price",
  "priority": "high",
  "condition_config": {
    "type": "price",
    "symbol": "NIFTY50",
    "operator": "gt",
    "threshold": 24000
  },
  "notification_channels": ["telegram"],
  "evaluation_interval_seconds": 60,
  "expires_at": "2025-12-31T23:59:59Z"
}

Response 201:
{
  "status": "success",
  "alert_id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2025-11-01T10:00:00Z",
  "next_evaluation_at": "2025-11-01T10:01:00Z"
}
```

```python
# List alerts
GET /alerts?status=active&alert_type=price&limit=50
Authorization: Bearer {api_key}

Response 200:
{
  "status": "success",
  "count": 25,
  "alerts": [
    {
      "alert_id": "...",
      "name": "NIFTY 24000 breakout",
      "status": "active",
      "trigger_count": 3,
      "last_triggered_at": "2025-11-01T09:45:00Z",
      ...
    }
  ]
}
```

```python
# Get alert details
GET /alerts/{alert_id}
Authorization: Bearer {api_key}

# Update alert
PUT /alerts/{alert_id}
Authorization: Bearer {api_key}

# Delete alert
DELETE /alerts/{alert_id}
Authorization: Bearer {api_key}
```

#### Alert Actions

```python
# Pause/Resume alert
POST /alerts/{alert_id}/pause
POST /alerts/{alert_id}/resume

# Acknowledge alert
POST /alerts/{alert_id}/acknowledge
{
  "event_id": "...",
  "note": "Position closed"
}

# Snooze alert
POST /alerts/{alert_id}/snooze
{
  "duration_seconds": 3600
}

# Test alert (dry-run evaluation)
POST /alerts/{alert_id}/test
Response:
{
  "would_trigger": true,
  "current_value": 24150,
  "threshold": 24000,
  "evaluation_time_ms": 45
}
```

#### Alert History

```python
# Get alert events
GET /alerts/{alert_id}/events?limit=100&status=triggered

# Get user's alert history
GET /alerts/history?from=2025-11-01&to=2025-11-30&priority=high
```

#### Notification Preferences

```python
# Get preferences
GET /notifications/preferences
Authorization: Bearer {api_key}

# Update preferences
PUT /notifications/preferences
{
  "telegram_enabled": true,
  "telegram_chat_id": "123456789",
  "quiet_hours_start": "22:00",
  "quiet_hours_end": "08:00",
  "max_notifications_per_hour": 30
}

# Setup Telegram (get bot link)
POST /notifications/telegram/setup
Response:
{
  "bot_username": "stocksblitz_alerts_bot",
  "setup_link": "https://t.me/stocksblitz_alerts_bot?start={verification_token}",
  "verification_token": "vfy_abc123...",
  "expires_in": 600
}
```

### 5.2 WebSocket Streaming

```python
# Real-time alert events
WS /alerts/stream?api_key={api_key}

# Client receives
{
  "type": "alert_triggered",
  "alert_id": "...",
  "event_id": "...",
  "name": "NIFTY 24000 breakout",
  "priority": "high",
  "trigger_value": {
    "current_price": 24150,
    "threshold": 24000
  },
  "triggered_at": "2025-11-01T14:35:20Z"
}

{
  "type": "alert_acknowledged",
  "alert_id": "...",
  "event_id": "...",
  "acknowledged_by": "user_xyz"
}
```

### 5.3 Webhook Callbacks

```python
# Telegram webhook (for interactive buttons)
POST /webhooks/telegram
X-Telegram-Bot-Api-Secret-Token: {secret}

# Receives callback_query from Telegram
{
  "callback_query": {
    "data": "ack:550e8400-e29b-41d4-a716-446655440000",
    "from": {"id": 123456789},
    "message": {...}
  }
}

# Parse and process
action, event_id = data.split(":")
if action == "ack":
    await alert_service.acknowledge_event(event_id, user_id)
    await telegram.answer_callback_query(
        callback_id,
        text="✅ Alert acknowledged"
    )
```

---

## 6. Evaluation Engine

### 6.1 Background Worker Architecture

```python
class AlertEvaluationWorker:
    """Background worker for continuous alert evaluation."""

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        redis: aioredis.Redis,
        ticker_service_url: str
    ):
        self.db_pool = db_pool
        self.redis = redis
        self.ticker_url = ticker_service_url
        self.evaluator = ConditionEvaluator(db_pool, redis, ticker_service_url)
        self.notifier = NotificationService(db_pool, redis)

    async def run(self):
        """Main evaluation loop."""
        logger.info("Starting alert evaluation worker")

        while True:
            try:
                # Fetch alerts due for evaluation
                alerts = await self.get_alerts_to_evaluate()

                if not alerts:
                    await asyncio.sleep(5)
                    continue

                # Evaluate in batches by priority
                batches = self.batch_by_priority(alerts)

                for priority, batch in batches.items():
                    # Process batch concurrently
                    tasks = [
                        self.evaluate_alert(alert)
                        for alert in batch
                    ]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    # Handle results
                    for alert, result in zip(batch, results):
                        if isinstance(result, Exception):
                            logger.error(f"Alert {alert['alert_id']} evaluation failed: {result}")
                            await self.mark_evaluation_error(alert['alert_id'], str(result))
                        elif result.triggered:
                            await self.handle_trigger(alert, result)

                await asyncio.sleep(1)  # Small delay between cycles

            except Exception as e:
                logger.error(f"Evaluation worker error: {e}", exc_info=True)
                await asyncio.sleep(5)  # Backoff on error

    async def get_alerts_to_evaluate(self) -> List[Dict]:
        """Fetch alerts that need evaluation based on interval."""
        query = """
            SELECT *
            FROM alerts
            WHERE status = 'active'
              AND (
                  last_evaluated_at IS NULL OR
                  last_evaluated_at + (evaluation_interval_seconds || ' seconds')::interval <= NOW()
              )
              AND (expires_at IS NULL OR expires_at > NOW())
              AND (
                  evaluation_window_start IS NULL OR
                  CURRENT_TIME BETWEEN evaluation_window_start AND evaluation_window_end
              )
            ORDER BY
                CASE priority
                    WHEN 'critical' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'medium' THEN 3
                    ELSE 4
                END,
                last_evaluated_at NULLS FIRST
            LIMIT 100
        """

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]

    async def evaluate_alert(self, alert: Dict) -> EvaluationResult:
        """Evaluate single alert condition."""
        try:
            # Check cooldown
            if not await self.check_cooldown(alert):
                return EvaluationResult(triggered=False, reason="cooldown")

            # Check daily trigger limit
            if not await self.check_daily_limit(alert):
                return EvaluationResult(triggered=False, reason="daily_limit_reached")

            # Evaluate condition
            result = await self.evaluator.evaluate(
                alert['condition_config'],
                context={
                    'user_id': alert['user_id'],
                    'account_id': alert['account_id'],
                    'symbol': alert['symbol']
                }
            )

            # Update evaluation timestamp
            await self.update_evaluation_timestamp(alert['alert_id'])

            return result

        except Exception as e:
            logger.error(f"Alert {alert['alert_id']} evaluation failed: {e}")
            raise

    async def handle_trigger(self, alert: Dict, result: EvaluationResult):
        """Handle alert trigger - create event and send notifications."""
        try:
            # Create alert event
            event_id = await self.create_alert_event(alert, result)

            # Send notifications
            await self.notifier.send_notifications(
                alert_id=alert['alert_id'],
                event_id=event_id,
                user_id=alert['user_id'],
                channels=alert['notification_channels'],
                message=self.format_message(alert, result),
                priority=alert['priority']
            )

            # Update alert state
            await self.update_alert_state(
                alert['alert_id'],
                trigger_count=alert['trigger_count'] + 1,
                last_triggered_at='NOW()',
                status='triggered' if alert.get('one_time') else 'active'
            )

            logger.info(f"Alert {alert['alert_id']} triggered: {alert['name']}")

        except Exception as e:
            logger.error(f"Failed to handle trigger for alert {alert['alert_id']}: {e}")
```

### 6.2 Condition Evaluator

```python
class ConditionEvaluator:
    """Evaluate alert conditions against current market data."""

    async def evaluate(
        self,
        condition_config: Dict,
        context: Dict
    ) -> EvaluationResult:
        """Main evaluation dispatcher."""
        condition_type = condition_config['type']

        evaluators = {
            'price': self.evaluate_price,
            'indicator': self.evaluate_indicator,
            'position': self.evaluate_position,
            'greek': self.evaluate_greek,
            'composite': self.evaluate_composite,
            'time': self.evaluate_time,
            'custom': self.evaluate_custom
        }

        evaluator = evaluators.get(condition_type)
        if not evaluator:
            raise ValueError(f"Unknown condition type: {condition_type}")

        return await evaluator(condition_config, context)

    async def evaluate_price(
        self,
        condition: Dict,
        context: Dict
    ) -> EvaluationResult:
        """Evaluate price-based condition."""
        symbol = condition.get('symbol') or context.get('symbol')

        # Fetch current price from ticker service
        current_data = await self.fetch_market_data(symbol)
        current_price = current_data.get('last_price')

        # Apply operator
        threshold = condition['threshold']
        operator = condition['operator']

        triggered = self.apply_operator(current_price, operator, threshold)

        return EvaluationResult(
            triggered=triggered,
            current_value=current_price,
            threshold=threshold,
            operator=operator,
            evaluation_data={'market_data': current_data}
        )

    async def evaluate_position(
        self,
        condition: Dict,
        context: Dict
    ) -> EvaluationResult:
        """Evaluate position-based condition."""
        account_id = context.get('account_id')
        symbol = condition.get('symbol')
        metric = condition['metric']  # pnl, quantity, pnl_percentage

        # Fetch position from database
        position = await self.fetch_position(account_id, symbol)

        if not position:
            return EvaluationResult(triggered=False, reason="position_not_found")

        current_value = position.get(metric)
        threshold = condition['threshold']
        operator = condition['operator']

        triggered = self.apply_operator(current_value, operator, threshold)

        return EvaluationResult(
            triggered=triggered,
            current_value=current_value,
            threshold=threshold,
            operator=operator,
            evaluation_data={'position': position}
        )

    async def evaluate_composite(
        self,
        condition: Dict,
        context: Dict
    ) -> EvaluationResult:
        """Evaluate composite AND/OR conditions."""
        operator = condition['operator']  # 'and' or 'or'
        sub_conditions = condition['conditions']

        results = []
        for sub_condition in sub_conditions:
            result = await self.evaluate(sub_condition, context)
            results.append(result)

        # Apply logical operator
        if operator == 'and':
            triggered = all(r.triggered for r in results)
        else:  # or
            triggered = any(r.triggered for r in results)

        return EvaluationResult(
            triggered=triggered,
            sub_results=results,
            composite_operator=operator
        )
```

### 6.3 Smart Batching & Optimization

**Symbol-Based Batching:**
```python
# Group alerts by symbol to batch data fetches
symbol_groups = defaultdict(list)
for alert in alerts:
    if alert['symbol']:
        symbol_groups[alert['symbol']].append(alert)

# Fetch market data once per symbol
for symbol, symbol_alerts in symbol_groups.items():
    market_data = await fetch_market_data(symbol)

    # Evaluate all alerts for this symbol
    for alert in symbol_alerts:
        result = evaluate_with_cached_data(alert, market_data)
```

**Redis Pub/Sub for Real-Time Triggers:**
```python
# Subscribe to ticker service price updates
async def subscribe_to_price_updates():
    pubsub = redis.pubsub()
    await pubsub.subscribe('ticker:nifty:ltp')

    async for message in pubsub.listen():
        if message['type'] == 'message':
            price_data = json.loads(message['data'])

            # Check active price alerts immediately
            await check_price_alerts(price_data['symbol'], price_data['ltp'])
```

---

## 7. User Service Integration

### 7.1 Current State (Phase 1)

**User Identification:**
- Use `user_id` from API key (existing `api_keys.user_id`)
- Single tenant per API key
- Notification preferences stored per `user_id`

```python
# Extract user from API key
@router.post("/alerts")
async def create_alert(
    request: AlertCreateRequest,
    api_key: APIKey = Depends(require_api_key)
):
    # User ID comes from authenticated API key
    user_id = api_key.user_id

    alert = await alert_service.create_alert(
        user_id=user_id,
        **request.dict()
    )
    return alert
```

### 7.2 Future State (Phase 2 - with user_service)

**Anticipated Integration Points:**

```python
# user_service will provide:
class UserService:
    async def get_user(self, user_id: str) -> User:
        """Get user profile."""
        pass

    async def get_notification_preferences(self, user_id: str) -> NotificationPreferences:
        """Get user's notification settings."""
        pass

    async def verify_user_access(self, user_id: str, resource: str) -> bool:
        """Check user's access permissions."""
        pass

    async def get_user_accounts(self, user_id: str) -> List[str]:
        """Get trading accounts linked to user."""
        pass
```

**Migration Path:**
1. Keep alert_service's own `notification_preferences` table
2. When user_service launches, add a sync mechanism
3. Use user_service as source of truth, alert_service as cache
4. Implement fallback to local preferences if user_service unavailable

**Design Considerations:**
- Alert service should work independently (resilience)
- Use circuit breaker pattern for user_service calls
- Cache user preferences in Redis (5-minute TTL)
- Implement graceful degradation

---

## 8. Python SDK Integration

### 8.1 SDK Alert Client

```python
# python-sdk/stocksblitz_sdk/services/alerts_v2.py

class AlertService:
    """Enhanced alert service with persistent backend."""

    def __init__(self, api_client: APIClient):
        self._api = api_client
        self._ws = None

    def create_price_alert(
        self,
        symbol: str,
        operator: str,  # 'gt', 'lt', 'gte', 'lte', 'eq'
        threshold: float,
        name: str = None,
        priority: str = 'medium',
        **kwargs
    ) -> str:
        """
        Create a price-based alert.

        Args:
            symbol: Trading symbol (e.g., "NIFTY50", "RELIANCE")
            operator: Comparison operator
            threshold: Price threshold
            name: Optional friendly name
            priority: Alert priority (low, medium, high, critical)
            **kwargs: Additional options (notification_channels, cooldown_seconds, etc.)

        Returns:
            alert_id: Unique alert identifier

        Example:
            >>> client = TradingClient(api_url="...", api_key="...")
            >>> alert_id = client.alerts.create_price_alert(
            ...     symbol="NIFTY50",
            ...     operator="gt",
            ...     threshold=24000,
            ...     name="NIFTY breakout",
            ...     priority="high"
            ... )
            >>> print(f"Alert created: {alert_id}")
        """
        payload = {
            "name": name or f"{symbol} {operator} {threshold}",
            "alert_type": "price",
            "priority": priority,
            "condition_config": {
                "type": "price",
                "symbol": symbol,
                "operator": operator,
                "threshold": threshold
            },
            **kwargs
        }

        response = self._api.post("/alerts", json=payload)
        return response["alert_id"]

    def create_position_alert(
        self,
        metric: str,  # 'pnl', 'day_pnl', 'quantity', 'pnl_percentage'
        operator: str,
        threshold: float,
        account_id: str = None,
        symbol: str = None,
        **kwargs
    ) -> str:
        """
        Create position-based alert (e.g., stop loss, profit target).

        Example:
            >>> # Alert when position loss exceeds ₹5,000
            >>> alert_id = client.alerts.create_position_alert(
            ...     metric="pnl",
            ...     operator="lt",
            ...     threshold=-5000,
            ...     priority="critical"
            ... )
        """
        payload = {
            "name": f"Position {metric} {operator} {threshold}",
            "alert_type": "position",
            "condition_config": {
                "type": "position",
                "metric": metric,
                "operator": operator,
                "threshold": threshold,
                "symbol": symbol
            },
            "account_id": account_id,
            **kwargs
        }

        response = self._api.post("/alerts", json=payload)
        return response["alert_id"]

    def create_indicator_alert(
        self,
        symbol: str,
        indicator: str,  # 'rsi', 'macd', 'sma', 'ema', etc.
        operator: str,
        threshold: float,
        timeframe: str = "5min",
        **kwargs
    ) -> str:
        """
        Create technical indicator alert.

        Example:
            >>> # Alert when RSI crosses 70 (overbought)
            >>> alert_id = client.alerts.create_indicator_alert(
            ...     symbol="NIFTY50",
            ...     indicator="rsi",
            ...     operator="gt",
            ...     threshold=70,
            ...     timeframe="5min"
            ... )
        """
        payload = {
            "name": f"{symbol} {indicator} {operator} {threshold}",
            "alert_type": "indicator",
            "condition_config": {
                "type": "indicator",
                "symbol": symbol,
                "indicator": indicator,
                "operator": operator,
                "threshold": threshold,
                "timeframe": timeframe
            },
            **kwargs
        }

        response = self._api.post("/alerts", json=payload)
        return response["alert_id"]

    def list_alerts(
        self,
        status: str = None,
        alert_type: str = None,
        limit: int = 50
    ) -> List[Dict]:
        """List user's alerts."""
        params = {}
        if status:
            params["status"] = status
        if alert_type:
            params["alert_type"] = alert_type
        params["limit"] = limit

        response = self._api.get("/alerts", params=params)
        return response["alerts"]

    def delete_alert(self, alert_id: str):
        """Delete an alert."""
        self._api.delete(f"/alerts/{alert_id}")

    def acknowledge(self, alert_id: str, event_id: str = None):
        """Acknowledge an alert event."""
        self._api.post(f"/alerts/{alert_id}/acknowledge", json={"event_id": event_id})

    def snooze(self, alert_id: str, duration_seconds: int = 3600):
        """Snooze an alert for specified duration."""
        self._api.post(f"/alerts/{alert_id}/snooze", json={"duration_seconds": duration_seconds})

    async def stream_events(self, callback: Callable):
        """
        Stream real-time alert events via WebSocket.

        Args:
            callback: Async function called on each event

        Example:
            >>> async def on_alert(event):
            ...     print(f"Alert triggered: {event['name']}")
            ...     print(f"Priority: {event['priority']}")
            ...
            ...     if event['priority'] == 'critical':
            ...         # Take action
            ...         client.alerts.acknowledge(event['alert_id'], event['event_id'])
            >>>
            >>> await client.alerts.stream_events(on_alert)
        """
        import websockets

        ws_url = self._api.base_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url += f"/alerts/stream?api_key={self._api.api_key}"

        async with websockets.connect(ws_url) as websocket:
            self._ws = websocket
            async for message in websocket:
                event = json.loads(message)
                await callback(event)
```

### 8.2 Usage Examples

**Simple Price Alert:**
```python
from stocksblitz_sdk import TradingClient

client = TradingClient(
    api_url="http://localhost:8082",
    api_key="sb_xxx_yyy"
)

# Create alert
alert_id = client.alerts.create_price_alert(
    symbol="NIFTY50",
    operator="gt",
    threshold=24000,
    priority="high",
    notification_channels=["telegram"],
    cooldown_seconds=300
)

print(f"Alert created: {alert_id}")
```

**Position Stop Loss:**
```python
# Monitor all positions for excessive loss
alert_id = client.alerts.create_position_alert(
    metric="pnl",
    operator="lt",
    threshold=-10000,
    priority="critical",
    notification_channels=["telegram"]
)
```

**Composite Alert (Multiple Conditions):**
```python
# Alert when NIFTY > 24000 AND RSI > 70 (potential reversal)
alert_id = client.alerts.create(
    name="NIFTY overbought at resistance",
    alert_type="custom",
    priority="high",
    condition_config={
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
)
```

**Real-Time Event Streaming:**
```python
import asyncio

async def handle_alert(event):
    print(f"🔔 {event['name']}")
    print(f"Priority: {event['priority']}")
    print(f"Triggered at: {event['triggered_at']}")

    # Auto-acknowledge critical alerts
    if event['priority'] == 'critical':
        client.alerts.acknowledge(event['alert_id'], event['event_id'])
        print("✅ Alert acknowledged")

# Stream events in background
asyncio.run(client.alerts.stream_events(handle_alert))
```

---

## 9. Configuration & Deployment

### 9.1 Configuration (Pydantic Settings)

```python
# alert_service/app/config.py

from pydantic_settings import BaseSettings
from typing import List, Optional

class Settings(BaseSettings):
    # Service
    app_name: str = "alert-service"
    environment: str = "development"
    port: int = 8082

    # Database (shared with backend)
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "stocksblitz_unified"
    db_user: str = "stocksblitz"
    db_password: str = "stocksblitz123"
    db_pool_min_size: int = 5
    db_pool_max_size: int = 20

    # Redis
    redis_url: str = "redis://localhost:6379/1"
    redis_cache_ttl: int = 300

    # External services
    backend_url: str = "http://localhost:8000"
    ticker_service_url: str = "http://localhost:8080"

    # Telegram Bot
    telegram_enabled: bool = True
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""

    # Evaluation settings
    evaluation_worker_enabled: bool = True
    evaluation_batch_size: int = 100
    evaluation_concurrency: int = 10
    min_evaluation_interval: int = 10  # seconds

    # Notification settings
    notification_rate_limit_per_user_per_hour: int = 50
    notification_retry_attempts: int = 3
    notification_retry_backoff: float = 2.0

    # Rate limiting
    global_telegram_rate_limit: int = 30  # messages/second

    # Security
    api_key_enabled: bool = True

    # Monitoring
    metrics_enabled: bool = True
    metrics_port: int = 9092
    log_level: str = "INFO"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8"
    }

@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

### 9.2 Docker Setup

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ ./app/
COPY migrations/ ./migrations/

# Health check
HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8082/health || exit 1

# Run
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8082", "--workers", "2"]
```

**docker-compose.yml (updated):**
```yaml
version: '3.8'

services:
  # ... existing services (redis, backend, ticker-service)

  alert-service:
    build: ./alert_service
    container_name: tv-alert-service
    ports:
      - "127.0.0.1:8082:8082"
      - "127.0.0.1:9092:9092"  # Metrics
    environment:
      - DB_HOST=host.docker.internal
      - DB_PORT=5432
      - DB_NAME=stocksblitz_unified
      - DB_USER=stocksblitz
      - DB_PASSWORD=stocksblitz123
      - REDIS_URL=redis://redis:6379/1
      - BACKEND_URL=http://backend:8000
      - TICKER_SERVICE_URL=http://ticker-service:8080
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - TELEGRAM_WEBHOOK_SECRET=${TELEGRAM_WEBHOOK_SECRET}
      - ENVIRONMENT=production
      - LOG_LEVEL=INFO
    depends_on:
      redis:
        condition: service_healthy
      backend:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8082/health"]
      interval: 15s
      timeout: 5s
      retries: 3
    networks:
      - tv-network
    extra_hosts:
      - "host.docker.internal:host-gateway"
    restart: unless-stopped
```

### 9.3 Environment Variables

**.env.example:**
```bash
# Alert Service Configuration

# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=stocksblitz_unified
DB_USER=stocksblitz
DB_PASSWORD=stocksblitz123

# Redis
REDIS_URL=redis://localhost:6379/1

# External Services
BACKEND_URL=http://localhost:8000
TICKER_SERVICE_URL=http://localhost:8080

# Telegram Bot
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_WEBHOOK_SECRET=change_me_in_production

# Worker Settings
EVALUATION_WORKER_ENABLED=true
EVALUATION_BATCH_SIZE=100
MIN_EVALUATION_INTERVAL=10

# Security
API_KEY_ENABLED=true

# Monitoring
METRICS_ENABLED=true
LOG_LEVEL=INFO

# Environment
ENVIRONMENT=production
```

---

## 10. Security & Rate Limiting

### 10.1 Authentication

**Reuse Existing API Key System:**
- Alert service validates API keys against backend's `api_keys` table
- Shared database access for seamless authentication
- User isolation via `user_id` from API key

```python
# alert_service/app/auth.py
from backend.app.auth import require_api_key, APIKey
# Reuse exact same authentication logic
```

### 10.2 Authorization

**Permissions:**
- `can_read`: View own alerts
- `can_create_alerts`: Create alerts (new permission)
- `can_manage_alerts`: Modify/delete alerts

**Row-Level Security:**
```sql
-- User can only see their own alerts
SELECT * FROM alerts WHERE user_id = {api_key.user_id}

-- Admin can see all alerts (future)
SELECT * FROM alerts WHERE user_id = {api_key.user_id} OR {api_key.is_admin}
```

### 10.3 Rate Limiting

**Per-User Limits:**
```python
# Redis-based token bucket
class RateLimiter:
    async def check_limit(self, user_id: str, limit: int, window_seconds: int) -> bool:
        """
        Token bucket algorithm.

        Args:
            user_id: User identifier
            limit: Max requests in window
            window_seconds: Time window

        Returns:
            True if allowed, False if rate limited
        """
        key = f"rate_limit:{user_id}:{window_seconds}"
        current = await self.redis.incr(key)

        if current == 1:
            await self.redis.expire(key, window_seconds)

        return current <= limit

# Apply to endpoints
@router.post("/alerts")
async def create_alert(
    request: AlertCreateRequest,
    api_key: APIKey = Depends(require_api_key)
):
    # Check rate limit: 100 alert creations per hour
    if not await rate_limiter.check_limit(api_key.user_id, limit=100, window_seconds=3600):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # ... create alert
```

**Notification Rate Limits:**
- Per user: 50 notifications/hour (configurable in preferences)
- Global Telegram: 30 messages/second (Bot API limit)
- Queue excess notifications for batch delivery

### 10.4 Input Validation

**Pydantic Models with Validation:**
```python
from pydantic import BaseModel, Field, validator

class AlertCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    alert_type: str = Field(..., pattern="^(price|indicator|position|greek|order|time|custom|strategy)$")
    priority: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    condition_config: Dict = Field(...)
    evaluation_interval_seconds: int = Field(default=60, ge=10, le=3600)

    @validator('condition_config')
    def validate_condition_config(cls, v, values):
        """Validate condition_config based on alert_type."""
        alert_type = values.get('alert_type')

        if alert_type == 'price':
            required_fields = ['type', 'operator', 'threshold']
            if not all(field in v for field in required_fields):
                raise ValueError(f"Price condition requires: {required_fields}")

        # ... other validations

        return v
```

---

## 11. Monitoring & Observability

### 11.1 Prometheus Metrics

```python
from prometheus_client import Counter, Histogram, Gauge, generate_latest

# Counters
alerts_created_total = Counter(
    'alerts_created_total',
    'Total alerts created',
    ['alert_type', 'priority']
)

alerts_triggered_total = Counter(
    'alerts_triggered_total',
    'Total alert triggers',
    ['alert_type', 'priority']
)

notifications_sent_total = Counter(
    'notifications_sent_total',
    'Total notifications sent',
    ['channel', 'status']
)

# Histograms
evaluation_duration_seconds = Histogram(
    'alert_evaluation_duration_seconds',
    'Alert evaluation duration',
    ['alert_type']
)

notification_delivery_duration_seconds = Histogram(
    'notification_delivery_duration_seconds',
    'Notification delivery duration',
    ['channel']
)

# Gauges
active_alerts_total = Gauge(
    'active_alerts_total',
    'Number of active alerts',
    ['alert_type', 'priority']
)

evaluation_queue_size = Gauge(
    'evaluation_queue_size',
    'Alerts waiting for evaluation'
)

# Expose metrics endpoint
@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type="text/plain")
```

### 11.2 Structured Logging

```python
import logging
import json
from datetime import datetime

class StructuredLogger:
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def info(self, message: str, **kwargs):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": "INFO",
            "message": message,
            **kwargs
        }
        self.logger.info(json.dumps(log_entry))

    def error(self, message: str, **kwargs):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": "ERROR",
            "message": message,
            **kwargs
        }
        self.logger.error(json.dumps(log_entry))

# Usage
logger = StructuredLogger("alert_service")

logger.info(
    "Alert triggered",
    alert_id=alert_id,
    user_id=user_id,
    alert_type=alert_type,
    trigger_value=trigger_value
)
```

### 11.3 Health Checks

```python
@app.get("/health")
async def health_check(db_pool: asyncpg.Pool = Depends(get_db_pool)):
    """
    Health check with dependency verification.
    """
    health_status = {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "alert-service",
        "version": "1.0.0"
    }

    # Check database
    try:
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        health_status["database"] = "healthy"
    except Exception as e:
        health_status["database"] = f"unhealthy: {e}"
        health_status["status"] = "degraded"

    # Check Redis
    try:
        await redis_client.ping()
        health_status["redis"] = "healthy"
    except Exception as e:
        health_status["redis"] = f"unhealthy: {e}"
        health_status["status"] = "degraded"

    # Check Telegram API
    if settings.telegram_enabled:
        try:
            response = await telegram_client.get_me()
            health_status["telegram"] = "healthy"
        except Exception as e:
            health_status["telegram"] = f"unhealthy: {e}"

    return health_status
```

---

## 12. Implementation Roadmap

### Phase 1: Core Infrastructure (Week 1-2)

**Week 1: Foundation**
- [ ] Set up alert_service folder structure
- [ ] Configure database connection (shared with backend)
- [ ] Create database migrations (alerts, alert_events, notification_preferences)
- [ ] Implement Pydantic models
- [ ] Set up Redis connection
- [ ] Implement API key authentication (reuse backend logic)
- [ ] Create basic FastAPI application with health endpoint
- [ ] Set up Docker configuration

**Week 2: Basic CRUD**
- [ ] Implement alert CRUD endpoints
- [ ] Create AlertService class
- [ ] Implement condition validation
- [ ] Add basic unit tests
- [ ] Set up logging
- [ ] Create integration tests
- [ ] Document API endpoints

### Phase 2: Evaluation Engine (Week 3-4)

**Week 3: Evaluator**
- [ ] Implement ConditionEvaluator base class
- [ ] Implement price condition evaluator
- [ ] Implement indicator condition evaluator
- [ ] Implement position condition evaluator
- [ ] Implement composite condition evaluator
- [ ] Add evaluation caching (Redis)
- [ ] Unit tests for each evaluator

**Week 4: Background Worker**
- [ ] Create AlertEvaluationWorker
- [ ] Implement evaluation scheduling
- [ ] Add priority-based batching
- [ ] Implement cooldown logic
- [ ] Add daily trigger limits
- [ ] Create evaluation metrics
- [ ] Load testing

### Phase 3: Notification System (Week 5-6)

**Week 5: Telegram Integration**
- [ ] Create NotificationService base class
- [ ] Implement TelegramProvider
- [ ] Set up Telegram bot
- [ ] Implement message formatting
- [ ] Add interactive buttons (acknowledge, snooze)
- [ ] Implement webhook endpoint for callbacks
- [ ] Test end-to-end notification flow

**Week 6: Notification Infrastructure**
- [ ] Implement notification_preferences management
- [ ] Add notification rate limiting
- [ ] Create notification retry logic
- [ ] Implement quiet hours
- [ ] Add notification_log tracking
- [ ] Create notification metrics
- [ ] Document Telegram setup process

### Phase 4: SDK & Testing (Week 7-8)

**Week 7: Python SDK**
- [ ] Create AlertService class in SDK
- [ ] Implement alert creation methods
- [ ] Add alert management methods
- [ ] Implement WebSocket streaming
- [ ] Create SDK examples
- [ ] Write SDK documentation
- [ ] Test SDK with real scenarios

**Week 8: Testing & Polish**
- [ ] Comprehensive integration tests
- [ ] Load testing (Locust)
- [ ] Security audit
- [ ] Performance optimization
- [ ] Documentation review
- [ ] Deployment guide
- [ ] User acceptance testing

### Phase 5: Advanced Features (Week 9-10)

**Week 9: Advanced Alerts**
- [ ] Implement greek condition evaluator
- [ ] Add time-based alerts
- [ ] Implement custom script evaluator (sandboxed)
- [ ] Add alert templates
- [ ] Create alert marketplace (optional)
- [ ] Backtesting for alerts (optional)

**Week 10: UI & Monitoring**
- [ ] Create Grafana dashboards
- [ ] Add alert management UI (frontend)
- [ ] Implement alert analytics
- [ ] Add performance optimizations
- [ ] Final documentation
- [ ] Production deployment

---

## Appendix A: Database Migration Files

See separate migration files in `/alert_service/migrations/`:
- `001_create_alerts.sql`
- `002_create_alert_events.sql`
- `003_create_notification_preferences.sql`
- `004_create_notification_log.sql`

## Appendix B: API Specification

OpenAPI/Swagger documentation will be auto-generated by FastAPI at:
- Development: `http://localhost:8082/docs`
- Production: `https://api.stocksblitz.com/alerts/docs`

## Appendix C: Telegram Bot Setup

Detailed guide for setting up Telegram bot, webhook configuration, and user verification flow.

---

**End of Design Document**

*Version: 1.0*
*Date: 2025-11-01*
*Author: StocksBlitz Engineering Team*
