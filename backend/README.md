# TradingView ML Visualization Backend

FastAPI-based backend service for TradingView ML visualization platform with F&O analytics, real-time data streaming, and trading strategy management.

## Features

- **Real-time Data**: WebSocket streaming for market data, F&O Greeks, and order updates
- **F&O Analytics**: Strike distribution, OI analysis, moneyness series, and Greeks calculations
- **Strategy Management**: Multi-instrument strategy tracking with real-time M2M calculation
- **Security**: JWT authentication, rate limiting, SQL injection protection
- **Caching**: Dual-layer caching (Memory → Redis → PostgreSQL)
- **Observability**: Prometheus metrics, structured JSON logging

## Prerequisites

- Python 3.11+
- PostgreSQL 16+ with TimescaleDB extension
- Redis 7+
- Ticker Service running on port 8080

## Quick Start

### 1. Environment Setup

```bash
# Clone repository
cd /path/to/tradingview-viz/backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

```bash
# Copy environment template
cp .env.template .env

# Edit .env with your credentials
nano .env
```

**Required environment variables**:
- `DB_PASSWORD`: PostgreSQL password
- `JWT_SECRET_KEY`: Secret key for JWT signing (generate with `openssl rand -hex 32`)

### 3. Database Setup

```bash
# Create database
createdb stocksblitz_unified

# Enable TimescaleDB extension
psql -d stocksblitz_unified -c "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"

# Run migrations (if using Alembic)
alembic upgrade head

# Or run SQL migrations manually
for f in migrations/*.sql; do
    psql -d stocksblitz_unified -f "$f"
done
```

### 4. Run Application

```bash
# Development mode with auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8081

# Production mode
uvicorn app.main:app --host 0.0.0.0 --port 8081 --workers 4
```

### 5. Verify Installation

```bash
# Health check
curl http://localhost:8081/health

# API documentation
open http://localhost:8081/docs  # Swagger UI
open http://localhost:8081/redoc  # ReDoc
```

## Project Structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI app, startup/shutdown
│   ├── config.py                # Settings (env vars, configuration)
│   ├── database.py              # Database connection pool, utilities
│   ├── cache.py                 # Dual-layer caching (Memory + Redis)
│   ├── dependencies.py          # FastAPI dependencies (auth, cache)
│   ├── routes/                  # API endpoints
│   │   ├── fo.py               # F&O analytics endpoints
│   │   ├── strategies.py       # Strategy management
│   │   ├── accounts.py         # Trading accounts
│   │   └── ...
│   ├── workers/                 # Background workers
│   │   └── strategy_m2m_worker.py  # M2M calculation
│   └── services/                # Business logic
├── tests/
│   ├── unit/                    # Unit tests
│   ├── integration/             # Integration tests
│   └── security/                # Security tests
├── migrations/                  # Database migrations (SQL or Alembic)
├── docs/                        # Documentation
│   ├── assessment_1/           # Production readiness assessment
│   └── assessment_2/           # Implementation status
├── requirements.txt             # Python dependencies
├── .env.template               # Environment variable template
└── README.md                    # This file
```

## API Endpoints

### Health & Metrics

- `GET /health` - Health check with DB/Redis status
- `GET /metrics` - Prometheus metrics

### F&O Analytics

- `GET /fo/strike-distribution` - Strike distribution with OI, volume, Greeks
- `GET /fo/oi-change` - OI change analysis (top gainers/losers)
- `GET /fo/moneyness-series` - Time series for Greeks by moneyness
- `WS /ws/fo/stream` - Real-time F&O data streaming

### Strategy Management

- `POST /strategies` - Create new strategy
- `GET /strategies` - List user strategies
- `GET /strategies/{id}` - Get strategy details
- `POST /strategies/{id}/instruments` - Add instrument to strategy
- `GET /strategies/{id}/m2m/timeseries` - M2M chart data

See `/docs` for complete API documentation.

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/unit/test_decimal_precision.py -v

# Run security tests only
pytest tests/security/ -v
```

**Test Coverage**: 49 tests (30 existing + 17 new security tests)
- SQL injection protection: 7 tests
- Decimal precision: 10 tests
- Expiry labeling: 30 tests
- Market depth analysis: 3 tests

## Security

### Authentication

- **JWT tokens**: Required for protected endpoints
- **WebSocket auth**: Token passed via query parameter `?token=<jwt>`
- **Rate limiting**: 100 requests/minute default (configurable per endpoint)

### SQL Injection Protection

All user-controlled parameters use:
- Parameterized queries (`$1`, `$2`, etc.)
- Whitelisted column names for sorting
- Input validation via Pydantic models

### Environment Variables

**NEVER commit `.env` to git**. All secrets are loaded from environment variables.

```bash
# Generate secure JWT secret
openssl rand -hex 32
```

## Configuration

### Environment Variables (`.env`)

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DB_PASSWORD` | PostgreSQL password | - | ✅ |
| `DB_HOST` | PostgreSQL host | localhost | ❌ |
| `DB_PORT` | PostgreSQL port | 5432 | ❌ |
| `DB_NAME` | Database name | stocksblitz_unified | ❌ |
| `DB_USER` | Database user | stocksblitz | ❌ |
| `REDIS_URL` | Redis connection URL | redis://localhost:6379 | ❌ |
| `JWT_SECRET_KEY` | JWT signing secret | - | ✅ |
| `JWT_ALGORITHM` | JWT algorithm | HS256 | ❌ |
| `TICKER_SERVICE_URL` | Ticker service URL | http://localhost:8080 | ❌ |
| `ENVIRONMENT` | Deployment environment | development | ❌ |

### Cache Configuration

```python
# app/config.py
cache_ttl_1m: int = 60      # 1-minute data TTL
cache_ttl_5m: int = 300     # 5-minute data TTL
cache_ttl_1h: int = 3600    # 1-hour data TTL
cache_ttl_1d: int = 86400   # 1-day data TTL
```

## Development

### Adding New Routes

```python
# app/routes/my_feature.py
from fastapi import APIRouter, Depends
from app.dependencies import get_cache_manager

router = APIRouter(prefix="/my-feature", tags=["My Feature"])

@router.get("/endpoint")
async def my_endpoint(cache = Depends(get_cache_manager)):
    return {"message": "Hello"}
```

```python
# app/main.py
from app.routes import my_feature

app.include_router(my_feature.router)
```

### Adding Background Workers

```python
# app/workers/my_worker.py
async def my_worker_task():
    while True:
        # Do work
        await asyncio.sleep(60)

# app/main.py - in lifespan startup
asyncio.create_task(my_worker_task())
```

## Deployment

### Docker

```bash
# Build image
docker build -t backend-api .

# Run container
docker run -d \
  --name backend \
  -p 8081:8081 \
  --env-file .env \
  backend-api
```

### Production Checklist

- [ ] Environment variables configured (`.env` in production secrets manager)
- [ ] Database migrations applied
- [ ] Redis accessible
- [ ] JWT secret is secure (32+ characters, random)
- [ ] CORS origins restricted to production domains
- [ ] Rate limiting configured for all public endpoints
- [ ] Monitoring & alerting setup (Prometheus + Grafana)
- [ ] Log aggregation configured (ELK, Loki, etc.)
- [ ] Backup strategy for PostgreSQL
- [ ] Health check endpoint monitored
- [ ] SSL/TLS certificates configured (reverse proxy)

## Monitoring

### Prometheus Metrics

Available at `/metrics`:

- `http_requests_total` - Total HTTP requests by method, path, status
- `http_request_duration_seconds` - Request duration histogram
- `db_pool_size` - Database connection pool size
- `db_pool_available` - Available database connections
- `redis_connected` - Redis connection status

### Health Check

```bash
# Check health
curl http://localhost:8081/health

# Response
{
  "status": "healthy",
  "database": "healthy",
  "redis": "healthy",
  "uptime": 3600,
  "version": "1.0.0",
  "cache_stats": {
    "l1_hits": 1000,
    "l2_hits": 500,
    "total_misses": 100,
    "hit_rate": 0.94
  }
}
```

## Troubleshooting

### Database Connection Issues

```bash
# Test PostgreSQL connection
psql -U stocksblitz -d stocksblitz_unified -h localhost

# Check connection pool
curl http://localhost:8081/health | jq '.cache_stats'
```

### Redis Connection Issues

```bash
# Test Redis connection
redis-cli ping

# Check Redis keys
redis-cli DBSIZE
```

### Application Won't Start

```bash
# Check logs
tail -f logs/app.log

# Verify environment variables
cat .env

# Test imports
python3 -c "from app.main import app; print('OK')"
```

## Contributing

1. Create feature branch: `git checkout -b feature/my-feature`
2. Make changes and add tests
3. Run tests: `pytest`
4. Commit changes: `git commit -m "feat: add my feature"`
5. Push branch: `git push origin feature/my-feature`
6. Create pull request

## License

Proprietary - All Rights Reserved

## Support

- **Documentation**: `/docs/assessment_1/` (production readiness assessment)
- **API Docs**: http://localhost:8081/docs (Swagger UI)
- **Issues**: Report issues to backend team

---

**Last Updated**: 2025-11-09
**Version**: 1.0.0
**Maintained By**: Backend Team
