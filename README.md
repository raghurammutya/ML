# TradingView ML Visualization System

High-performance web application for visualizing Nifty50 OHLC data with ML-generated sentiment labels using TradingView's Advanced Chart widget.

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose installed
- TimescaleDB running with stocksblitz_unified database
- Port 8000 (backend) and 3000 (frontend) available

### Installation

1. **Start the system:**
   ```bash
   docker-compose up -d
   ```

2. **Verify health:**
   ```bash
   curl http://localhost:8000/health | jq
   ```

3. **Warm up cache (recommended):**
   ```bash
   python scripts/cache_warmup.py
   ```

4. **Access the application:**
   ```
   http://localhost:3000
   ```

## 📊 Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   TradingView   │────▶│   FastAPI       │────▶│   TimescaleDB   │
│   Frontend      │     │   Backend       │     │   Database      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌─────────────────┐
                        │     Redis       │
                        │     Cache       │
                        └─────────────────┘
```

## 🔧 Configuration

### Environment Variables (.env)
```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=stocksblitz_unified
DB_USER=stocksblitz
DB_PASSWORD=stocksblitz123
REDIS_URL=redis://localhost:6379
```

### Supported Resolutions
- 1, 5, 15, 30, 60 minutes
- D (Daily), W (Weekly), M (Monthly)

## 📈 Performance Metrics

| Metric | Target | Actual |
|--------|--------|--------|
| Response Time (P50) | <50ms | - |
| Response Time (P95) | <200ms | - |
| Cache Hit Rate | >80% | - |
| Concurrent Users | 1000+ | - |

## 🧪 Testing

### Test Endpoints
```bash
./scripts/test_endpoints.sh
```

### Load Testing
```bash
# Simple load test
python scripts/load_test.py

# Advanced load test with Locust
locust -f scripts/load_test.py --host=http://localhost:8000 --users=1000 --spawn-rate=50
```

### Performance Test
```bash
python scripts/test_system.py
```

## 📡 API Endpoints

### TradingView UDF Protocol
- `GET /config` - Chart configuration
- `GET /symbols` - Symbol information
- `GET /search` - Symbol search
- `GET /history` - Historical OHLC data
- `GET /marks` - ML sentiment labels
- `GET /timescale_marks` - Detailed ML labels

### System Endpoints
- `GET /health` - Health check
- `GET /metrics` - Prometheus metrics
- `GET /cache/stats` - Cache statistics
- `GET /api/label-distribution` - ML label distribution

## 🔍 Monitoring

### Cache Statistics
```bash
curl http://localhost:8000/cache/stats | jq
```

### Prometheus Metrics
```bash
curl http://localhost:8000/metrics
```

### Docker Stats
```bash
docker stats tv-backend tv-redis tv-frontend
```

## 🚨 Troubleshooting

### High Cache Miss Rate
```bash
# Check cache keys
docker exec -it tv-redis redis-cli --scan --pattern "history:*" | wc -l

# Increase cache warmup
python scripts/cache_warmup.py --days 14
```

### Slow Response Times
```bash
# Check database indexes
docker exec -it stocksblitz-postgres psql -U stocksblitz -d stocksblitz_unified -c "\di"

# Check pool connections
curl http://localhost:8000/health | jq '.cache_stats'
```

### Memory Issues
```bash
# Reduce preload size
docker-compose stop backend
PRELOAD_DAYS=7 PRELOAD_MAX_RECORDS=10000 docker-compose up -d backend
```

## 🏗️ Development

### Backend Development
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend Development
```bash
cd frontend
npm install
npm run dev
```

## 📄 TradingView Integration

To enable the full TradingView charting library:

1. Apply for library access at [TradingView](https://www.tradingview.com/HTML5-stock-forex-bitcoin-charting-library/)
2. Download the charting library
3. Extract to `frontend/public/charting_library/`
4. Restart the frontend container

## 🔐 Security

- Input validation on all endpoints
- Rate limiting configured
- CORS properly configured
- SQL injection prevention
- No sensitive data in logs

## 📊 Database Schema

### Tables Used
- `nifty50_ohlc` - 1-minute OHLC data
- `ml_labeled_data` - ML sentiment labels
- `nifty50_5min`, `nifty50_15min`, `nifty50_daily` - Continuous aggregates

## 🎯 Performance Optimization

1. **Three-layer caching:**
   - L1: In-memory cache (instant)
   - L2: Redis cache (1-5ms)
   - L3: Database (100-300ms)

2. **Data preloading:**
   - Last 30 days preloaded on startup
   - Refresh every 5 minutes

3. **Connection pooling:**
   - Min 10, Max 20 database connections
   - Async operations throughout

## 📝 License

Proprietary - All rights reserved

## 👥 Support

For issues or questions, please contact the development team.