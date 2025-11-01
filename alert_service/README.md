# Alert Service

Real-time trading alerts and notifications for StocksBlitz platform.

## Overview

The Alert Service provides:
- Real-time price, indicator, and position alerts
- Telegram notifications (extensible to FCM, APNS, email)
- Background evaluation engine with priority-based scheduling
- WebSocket streaming for real-time events
- Persistent alert history in TimescaleDB

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL with TimescaleDB extension (shared with backend)
- Redis
- Telegram Bot Token

### Installation

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env
# Edit .env with your configuration
```

### Run Locally

```bash
# Run database migrations (from project root)
psql -U stocksblitz -d stocksblitz_unified -f migrations/001_create_alerts.sql

# Start service
uvicorn app.main:app --reload --port 8082
```

Access the API:
- **API Docs**: http://localhost:8082/docs
- **Health Check**: http://localhost:8082/health
- **Metrics**: http://localhost:9092/metrics

### Run with Docker

```bash
# Build image
docker build -t alert-service .

# Run container
docker run -p 8082:8082 -p 9092:9092 \
  --env-file .env \
  alert-service
```

## Architecture

```
alert_service/
├── app/
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration (Pydantic Settings)
│   ├── database.py          # Database connection pool
│   ├── routes/
│   │   ├── alerts.py        # Alert CRUD endpoints
│   │   └── notifications.py # Notification management
│   ├── services/
│   │   ├── alert_service.py        # Core alert logic
│   │   ├── evaluator.py            # Condition evaluation
│   │   ├── notification_service.py # Notification dispatch
│   │   └── providers/
│   │       ├── telegram.py         # Telegram Bot API
│   │       └── base.py             # Provider abstraction
│   ├── models/
│   │   ├── alert.py         # Alert Pydantic models
│   │   └── condition.py     # Condition models
│   └── background/
│       └── evaluation_worker.py # Background evaluation loop
├── migrations/
│   ├── 001_create_alerts.sql
│   ├── 002_create_alert_events.sql
│   └── 003_create_notification_preferences.sql
└── tests/
    ├── unit/
    └── integration/
```

## Database Schema

### Core Tables

1. **alerts** - Alert definitions
2. **alert_events** - Trigger history (TimescaleDB hypertable)
3. **notification_preferences** - User notification settings
4. **notification_log** - Delivery tracking (TimescaleDB hypertable)

See `migrations/` for full schema.

## API Endpoints

### Alert Management

```bash
# Create alert
POST /alerts
{
  "name": "NIFTY 24000 breakout",
  "alert_type": "price",
  "priority": "high",
  "condition_config": {
    "type": "price",
    "symbol": "NIFTY50",
    "operator": "gt",
    "threshold": 24000
  }
}

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
```

### Notifications

```bash
# Get preferences
GET /notifications/preferences

# Update preferences
PUT /notifications/preferences
```

## Alert Types

- **price**: Price-based alerts (e.g., "NIFTY > 24000")
- **indicator**: Technical indicators (e.g., "RSI > 70")
- **position**: Position-based (e.g., "P&L < -5000")
- **greek**: Option Greeks (e.g., "Delta > 0.5")
- **composite**: Multiple conditions (AND/OR)
- **time**: Time-based reminders

## Configuration

See `.env.example` for all configuration options.

Key settings:
- `TELEGRAM_BOT_TOKEN`: Telegram bot token
- `MIN_EVALUATION_INTERVAL`: Minimum seconds between evaluations (default: 10)
- `NOTIFICATION_RATE_LIMIT_PER_USER_PER_HOUR`: Max notifications per user per hour (default: 50)

## Development

### Run Tests

```bash
# Unit tests
pytest tests/unit/

# Integration tests
pytest tests/integration/

# All tests with coverage
pytest --cov=app tests/
```

### Code Quality

```bash
# Format code
black app/

# Lint code
ruff check app/
```

## Monitoring

### Prometheus Metrics

Metrics available at `http://localhost:9092/metrics`:

- `alerts_created_total{alert_type, priority}` - Total alerts created
- `alerts_triggered_total{alert_type, priority}` - Total alert triggers
- `notifications_sent_total{channel, status}` - Total notifications sent
- `evaluation_duration_seconds{alert_type}` - Alert evaluation duration
- `active_alerts_total{alert_type, priority}` - Number of active alerts

### Health Check

```bash
curl http://localhost:8082/health
```

Returns:
```json
{
  "status": "ok",
  "database": "healthy",
  "redis": "healthy",
  "telegram": "healthy"
}
```

## Deployment

### Docker Compose

See `docker-compose.yml` in project root for full setup.

```yaml
services:
  alert-service:
    build: ./alert_service
    ports:
      - "8082:8082"
      - "9092:9092"
    environment:
      - DB_HOST=host.docker.internal
      - REDIS_URL=redis://redis:6379/1
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
```

## Troubleshooting

### Database Connection Failed

- Verify PostgreSQL is running
- Check database credentials in `.env`
- Ensure TimescaleDB extension is installed

### Telegram Notifications Not Working

- Verify `TELEGRAM_BOT_TOKEN` is set correctly
- Check bot has permission to send messages
- Verify user has started conversation with bot

### High Memory Usage

- Reduce `EVALUATION_BATCH_SIZE` (default: 100)
- Decrease `DB_POOL_MAX_SIZE` (default: 20)
- Lower `EVALUATION_CONCURRENCY` (default: 10)

## Support

- **API Documentation**: http://localhost:8082/docs
- **Design Document**: ../ALERT_SERVICE_DESIGN.md
- **Quick Start Guide**: ../ALERT_SERVICE_QUICK_START.md

## License

Proprietary - StocksBlitz
