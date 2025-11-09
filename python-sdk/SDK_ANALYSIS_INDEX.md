# StocksBlitz Python SDK - Analysis Index

## Overview

Complete analysis of the **StocksBlitz Python SDK v0.2.0** - a production-ready Python interface for algorithmic trading with dual authentication, 40+ technical indicators, and enterprise-grade features.

**SDK Location:** `/mnt/stocksblitz-data/Quantagro/tradingview-viz/python-sdk/`

---

## Analysis Documents

### 1. SDK_COMPREHENSIVE_ANALYSIS.md (27 KB)
**Complete technical deep dive covering all aspects of the SDK**

Contents:
- Executive summary
- SDK structure and architecture (13 core modules + 4 services)
- Authentication methods (JWT vs API Key)
- Client initialization options (4 patterns)
- Support for different user types (5 types)
- SDK components deep dive
- Data models and type safety (17 enums, 8+ dataclasses)
- Caching strategy
- Production readiness checklist
- Code statistics and file references
- Usage examples and conclusion

**Best For:** In-depth understanding of SDK capabilities, architecture, and implementation details

---

### 2. SDK_SUMMARY.txt (402 lines)
**Quick reference guide with key information in plain text format**

Sections:
1. SDK Overview
2. Authentication (Dual support explanation)
3. Client Initialization (4 patterns)
4. User Service Integration Points
5. Architecture diagram
6. Key Components
7. User Type Support
8. Authentication Flow
9. Security Features
10. Caching Strategy
11. Indicators List
12. Type Safety Details
13. Error Handling
14. Usage Examples
15. Documentation Files
16. Roadmap
17. Files Reference
18. Quick Start for Different Use Cases
19. Comparison with Alternatives
20. Conclusion

**Best For:** Quick lookup, sharing with team, reference guide

---

## Key Findings

### SDK Statistics
- **Total Code:** 6,697 Python lines
- **Core Modules:** 13 (client, api, instrument, account, strategy, filter, indicators, etc.)
- **Service Modules:** 4 (alerts, messaging, calendar, news)
- **Dependencies:** Only 1 (httpx for HTTP)
- **Python Support:** 3.8 - 3.12
- **Version:** 0.2.0 (Production)

### Authentication Methods

**JWT Authentication (User-Facing)**
```
Setup: TradingClient.from_credentials(api_url, user_service_url, username, password)
Tokens: 15 min access + 30 day refresh
Auto-refresh: Yes (transparent)
Endpoints:
  - POST /v1/auth/login
  - POST /v1/auth/refresh
  - POST /v1/auth/logout
```

**API Key Authentication (Server-to-Server)**
```
Setup: TradingClient(api_url, api_key="sb_...")
Lifetime: Indefinite (until revoked)
Auto-refresh: N/A (no tokens)
Security: SHA-256 hashing, IP whitelist, rate limits
```

### User Service Integration

The SDK integrates with **user_service** via these endpoints:

1. **POST /v1/auth/login** - User authentication
   - Request: `{email, password, persist_session}`
   - Response: `{access_token, refresh_token, expires_in, user}`

2. **POST /v1/auth/refresh** - Token refresh
   - Request: `refresh_token` (cookie)
   - Response: `{access_token, expires_in}`

3. **POST /v1/auth/logout** - Session cleanup
   - Request: `Authorization: Bearer {access_token}`
   - Response: `{status: "ok"}`

4. **GET /v1/auth/.well-known/jwks.json** - JWKS keys (used by backend)

### Client Initialization Patterns

**Pattern 1: JWT with from_credentials (Recommended for Users)**
```python
client = TradingClient.from_credentials(
    api_url="http://localhost:8081",
    user_service_url="http://localhost:8001",
    username="trader@example.com",
    password="password",
    persist_session=True
)
```

**Pattern 2: JWT with manual login**
```python
client = TradingClient(
    api_url="http://localhost:8081",
    user_service_url="http://localhost:8001"
)
client.login("trader@example.com", "password")
```

**Pattern 3: API Key**
```python
client = TradingClient(
    api_url="http://localhost:8081",
    api_key="sb_30d4d5ea_..."
)
```

**Pattern 4: Custom cache**
```python
client = TradingClient(
    api_url="http://localhost:8081",
    api_key="sb_...",
    enable_disk_cache=True,
    cache_ttl=3600
)
```

### Support for Different User Types

1. **Individual Traders**
   - Auth: JWT with from_credentials()
   - Use: Jupyter notebooks, interactive trading
   - Features: Full trading, strategy creation, alerts

2. **Automated Bots**
   - Auth: API Key
   - Use: 24/7 background services
   - Features: All trading operations, strategy execution

3. **Institutional Systems**
   - Auth: Multiple API keys
   - Use: Multi-account portfolio management
   - Features: Risk management, compliance tracking

4. **Data Scientists**
   - Auth: Read-only API key (future)
   - Use: Bulk data download, backtesting
   - Features: Data access only

5. **Integration Partners**
   - Auth: Scoped API key
   - Use: Third-party integrations
   - Features: Service-to-service communication

### Core Components

**Trading:**
- Instrument (symbols, OHLCV, Greeks)
- Account (portfolio, orders, positions)
- Strategy (isolated execution, metrics)
- Position (open positions, P&L)

**Advanced:**
- InstrumentFilter (pattern-based search)
- 40+ Indicators (RSI, MACD, SMA, EMA, etc.)
- Option Greeks (Delta, Gamma, Theta, Vega, IV)

**Services:**
- AlertService (event-based alerts)
- MessagingService (pub/sub)
- CalendarService (reminders)
- NewsService (sentiment analysis)

### Type Safety

**17 Enum Classes:**
DataState, Exchange, TransactionType, OrderType, ProductType, Validity, OrderStatus, PositionType, Timeframe, AlertType, AlertPriority, MessageType, ReminderFrequency, NewsCategory, NewsSentiment, StrategyType, StrategyStatus

**8+ Dataclasses:**
AlertEvent, Message, Reminder, NewsItem, OrderRequest, QuoteData, GreeksData, MarketDepth, LiquidityMetrics, FuturesPosition, RolloverMetrics, StrategyMetrics

### Security Features

**JWT:**
- Short-lived access tokens (15 minutes)
- Long-lived refresh tokens (30 days)
- RS256 signature verification
- Automatic token rotation
- Passwords never stored

**API Key:**
- SHA-256 hashing
- IP whitelisting
- Rate limiting
- Permission-based access
- Account restrictions
- Audit trail

---

## Related Documentation

### Official SDK Documentation
- **README.md** - User guide with 50+ examples
- **AUTHENTICATION.md** - Complete authentication guide (400+ lines)
- **SDK_AUTH_IMPLEMENTATION.md** - Technical implementation details
- **setup.py** - Package configuration
- **requirements.txt** - Dependencies (only httpx)

### Working Examples
- **examples/jwt_auth_example.py** - JWT authentication example
- **examples/api_key_auth_example.py** - API Key authentication example

### Implementation Details
- **stocksblitz/client.py** - Main TradingClient class
- **stocksblitz/api.py** - HTTP client with auth
- **stocksblitz/instrument.py** - Instrument and indicator handling
- **stocksblitz/account.py** - Account and position management
- **stocksblitz/strategy.py** - Strategy management
- **stocksblitz/services/** - Advanced services (alerts, messaging, etc.)

---

## Quick Reference

### Create Client (JWT)
```python
from stocksblitz import TradingClient

client = TradingClient.from_credentials(
    api_url="http://localhost:8081",
    user_service_url="http://localhost:8001",
    username="trader@example.com",
    password="password"
)
```

### Create Client (API Key)
```python
from stocksblitz import TradingClient
import os

client = TradingClient(
    api_url="http://localhost:8081",
    api_key=os.getenv("STOCKSBLITZ_API_KEY")
)
```

### Basic Trading
```python
inst = client.Instrument("NIFTY50")
print(f"RSI: {inst['5m'].rsi[14]}")
print(f"LTP: {inst.ltp}")

account = client.Account()
account.buy(inst, quantity=50)
```

### Strategy
```python
strategy = client.Strategy(
    strategy_name="RSI Mean Reversion",
    strategy_type="mean_reversion"
)

with strategy:
    inst = client.Instrument("NIFTY50")
    if inst['5m'].rsi[14] < 30:
        strategy.buy(inst, quantity=50)
```

### Alerts
```python
client.alerts.raise_alert(
    alert_type=AlertType.PRICE,
    priority=AlertPriority.HIGH,
    symbol="NIFTY50",
    message="Price crossed 24000"
)
```

---

## Architecture Overview

```
TradingClient (Entry Point)
├── APIClient (HTTP + Auth)
│   ├── JWT Management (_access_token, _refresh_token, _token_expires_at)
│   ├── API Key Management (_api_key)
│   └── Auto-refresh Logic
├── Instrument (Trading Symbols)
│   ├── TimeframeProxy (1m, 5m, 15m, 1h, 1d)
│   │   └── Candle (OHLCV)
│   │       └── IndicatorProxy (40+ indicators)
│   └── Greeks (Delta, Gamma, Theta, Vega, IV)
├── Account (Portfolio)
│   ├── Position
│   ├── Order
│   └── Funds
├── Strategy (Isolated Trading)
│   └── StrategyMetrics (P&L, ROI, Sharpe)
├── InstrumentFilter (Pattern Search)
├── Services
│   ├── AlertService
│   ├── MessagingService
│   ├── CalendarService
│   └── NewsService
└── IndicatorRegistry (Validation + Caching)
```

---

## Roadmap (v0.3.0+)

Planned Features:
- WebSocket streaming support
- Strategy backtesting framework
- Performance analytics dashboard
- Advanced risk management tools
- Portfolio optimization
- Redis caching backend

---

## Production Readiness

### Current Status: Production-Ready ✅

**Checklist:**
- ✅ Dual authentication (JWT + API Key)
- ✅ 40+ technical indicators
- ✅ Multi-timeframe analysis
- ✅ Options Greeks
- ✅ Order management
- ✅ Position tracking
- ✅ Strategy isolation
- ✅ Multi-account support
- ✅ Type hints (full IDE support)
- ✅ Comprehensive error handling
- ✅ Caching (in-memory + disk)
- ✅ Rate limiting support
- ✅ Full documentation

---

## File Structure

**SDK Package:** `/mnt/stocksblitz-data/Quantagro/tradingview-viz/python-sdk/`

```
stocksblitz/                          # Main package
├── __init__.py                       # Public API
├── client.py                         # TradingClient
├── api.py                            # APIClient
├── instrument.py                     # Instrument + Candle
├── account.py                        # Account + Position + Order
├── strategy.py                       # Strategy management
├── filter.py                         # InstrumentFilter
├── indicators.py                     # IndicatorProxy
├── indicator_registry.py             # Registry + caching
├── cache.py                          # Caching logic
├── enums.py                          # 17 enum classes
├── types.py                          # Type definitions
├── exceptions.py                     # Exception classes
└── services/                         # Advanced services
    ├── alerts.py                     # AlertService
    ├── messaging.py                  # MessagingService
    ├── calendar.py                   # CalendarService
    └── news.py                       # NewsService
```

---

## Next Steps

1. **For Understanding the SDK:**
   - Read `SDK_COMPREHENSIVE_ANALYSIS.md` for full technical details
   - Review `examples/` for working code
   - Check `AUTHENTICATION.md` for auth deep dive

2. **For Using the SDK:**
   - Start with `README.md` examples
   - Choose authentication method (JWT for users, API Key for bots)
   - Use `TradingClient.from_credentials()` for easy setup
   - Check error handling with exception classes

3. **For Integration:**
   - Review `stocksblitz/api.py` for user_service endpoints
   - Understand token refresh logic in `_get_auth_header()`
   - Check JWKS integration with backend

4. **For Advanced Usage:**
   - Use `Strategy` for isolated P&L tracking
   - Use `InstrumentFilter` for pattern-based search
   - Use services for alerts, messaging, calendar, news
   - Use `IndicatorRegistry` for validation

---

## Questions Answered by This Analysis

### 1. SDK Structure
- **Q:** What are the main components?
- **A:** 13 core modules + 4 services, see section "SDK Structure and Architecture"

### 2. Authentication
- **Q:** How does the SDK authenticate with user_service?
- **A:** See "Authentication Methods" and "User Service Integration"

### 3. Client Initialization
- **Q:** How do I initialize the client?
- **A:** 4 patterns provided in "Client Initialization Patterns"

### 4. User Types
- **Q:** Does the SDK support different user types?
- **A:** Yes, 5 types covered in "Support for Different User Types"

### 5. Security
- **Q:** How secure are JWT and API Key auth?
- **A:** See "Security Features" section

### 6. Capabilities
- **Q:** What can the SDK do?
- **A:** Trading, strategy management, indicators, alerts, messaging, calendar, news

### 7. Integration with user_service
- **Q:** What endpoints does SDK call?
- **A:** 4 endpoints listed in "User Service Integration Points"

---

## Document Information

- **Created:** 2025-11-09
- **SDK Version Analyzed:** 0.2.0
- **Analysis Scope:** Complete SDK capabilities, authentication, architecture
- **Files Generated:**
  - SDK_COMPREHENSIVE_ANALYSIS.md (27 KB)
  - SDK_SUMMARY.txt (402 lines)
  - SDK_ANALYSIS_INDEX.md (this file)

---

**For detailed information, see SDK_COMPREHENSIVE_ANALYSIS.md**

