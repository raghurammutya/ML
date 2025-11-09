# StocksBlitz Python SDK - Comprehensive Analysis

## Executive Summary

The **StocksBlitz Python SDK** (v0.2.0) is a comprehensive, production-ready Python interface for algorithmic trading with the StocksBlitz platform. It spans **6,697 lines of Python code** across **13 core modules** plus services, with support for 40+ technical indicators, dual authentication, and enterprise-grade trading operations.

**Key Characteristics:**
- Pythonic API with lazy evaluation and smart caching
- Dual authentication (JWT for users, API keys for services)
- Multi-timeframe technical analysis
- Strategy management with isolated P&L tracking
- Advanced services (Alerts, Messaging, Calendar, News)
- Full type hints with IDE autocomplete

---

## 1. SDK Structure and Architecture

### Directory Layout
```
python-sdk/
├── stocksblitz/                    # Main SDK package (13 modules)
│   ├── __init__.py                 # Public API exports (v0.2.0)
│   ├── client.py                   # TradingClient (main entry point)
│   ├── api.py                       # APIClient (HTTP + auth)
│   ├── instrument.py                # Instrument + Candle + TimeframeProxy
│   ├── account.py                   # Account + Position + Order + Funds
│   ├── strategy.py                  # Strategy + StrategyMetrics
│   ├── filter.py                    # InstrumentFilter (pattern-based search)
│   ├── indicators.py                # IndicatorProxy (40+ indicators)
│   ├── indicator_registry.py        # IndicatorRegistry (caching + validation)
│   ├── cache.py                     # SimpleCache (in-memory + disk)
│   ├── enums.py                     # 17 enum classes (OrderType, Timeframe, etc)
│   ├── types.py                     # 8+ dataclass models (AlertEvent, Message, etc)
│   ├── exceptions.py                # 11 exception types
│   └── services/                    # 4 advanced services
│       ├── alerts.py                # AlertService (event-based)
│       ├── messaging.py             # MessagingService (pub/sub)
│       ├── calendar.py              # CalendarService (reminders)
│       └── news.py                  # NewsService (sentiment analysis)
├── examples/                        # Authentication examples
│   ├── jwt_auth_example.py
│   └── api_key_auth_example.py
├── tests/                           # Test suite
├── README.md                        # User guide
├── AUTHENTICATION.md                # Auth guide
├── setup.py                         # Package configuration
└── requirements.txt                 # httpx only
```

### Code Statistics
- **Total Lines:** 6,697 Python lines
- **Core Modules:** 13
- **Service Modules:** 4
- **Example Scripts:** 2
- **Documentation:** 6 comprehensive guides
- **Dependencies:** 1 (httpx)

### Module Relationships
```
TradingClient (entry point)
├── APIClient (HTTP + auth management)
├── Instrument (trading symbols)
│   ├── TimeframeProxy (1m, 5m, 15m, 1h, 1d)
│   │   └── Candle (OHLCV + indicators)
│   │       └── IndicatorProxy (40+ indicators)
├── Account (portfolio operations)
│   ├── Position (open positions)
│   ├── Order (order management)
│   └── Funds (margin + cash)
├── Strategy (isolated strategy trading)
├── InstrumentFilter (pattern-based search)
├── Services
│   ├── AlertService
│   ├── MessagingService
│   ├── CalendarService
│   └── NewsService
└── IndicatorRegistry (validation + caching)
```

---

## 2. Authentication Methods

### Overview
The SDK implements **dual authentication** to support different use cases:

| Feature | JWT Auth | API Key Auth |
|---------|----------|--------------|
| **Use Case** | User-facing apps | Server-to-server bots |
| **Credentials** | Email + password | Long-lived API key |
| **Token Lifetime** | 15 min (access), 30 days (refresh) | Indefinite |
| **Auto-refresh** | Yes | N/A |
| **Session Management** | Yes | No |
| **Setup** | 1-step (from_credentials) | Pass api_key |

### Authentication Flow

#### JWT Authentication (User-Facing)

**Architecture:**
```
Python SDK                    User Service               Backend API
    │                             │                           │
    ├─ login(user@, pwd)         │                           │
    │─────────────────────────────>│                           │
    │                             │ Validate credentials       │
    │                             │ Issue JWT tokens          │
    │<─ access_token + refresh    │                           │
    │    (15 min, 30 days)         │                           │
    │                             │                           │
    │ Auto-refresh before expiry  │                           │
    ├─ POST /v1/auth/refresh ─────>│                           │
    │<─ new access_token          │                           │
    │                             │                           │
    ├─ GET /api/endpoint (JWT) ────────────────────────────────>│
    │                             │                           │
    │<───────────────────────────────── Response with data     │
    │                             │                           │
```

**Implementation in `api.py`:**

```python
def _get_auth_header(self) -> Dict[str, str]:
    """Get auth header with automatic token refresh."""
    if self._access_token:
        # Check if expiring within 60 seconds
        if self._token_expires_at and time.time() >= self._token_expires_at - 60:
            self._refresh_access_token()
        return {"Authorization": f"Bearer {self._access_token}"}
    
    elif self._api_key:
        return {"Authorization": f"Bearer {self._api_key}"}
    
    else:
        raise AuthenticationError("No authentication configured")

def login(self, username: str, password: str, persist_session: bool = True):
    """Login to user_service and obtain JWT tokens."""
    response = httpx.post(
        f"{self.user_service_url}/v1/auth/login",
        json={
            "email": username,
            "password": password,
            "persist_session": persist_session  # Get refresh token
        }
    )
    
    # Store tokens
    self._access_token = response.json()["access_token"]
    self._refresh_token = response.json()["refresh_token"]
    self._token_expires_at = time.time() + response.json()["expires_in"]

def _refresh_access_token(self):
    """Auto-refresh using refresh_token from user_service."""
    response = httpx.post(
        f"{self.user_service_url}/v1/auth/refresh",
        cookies={"refresh_token": self._refresh_token}
    )
    self._access_token = response.json()["access_token"]
    self._token_expires_at = time.time() + response.json()["expires_in"]
```

**Usage:**

```python
# Method 1: One-step (recommended)
client = TradingClient.from_credentials(
    api_url="http://localhost:8081",
    user_service_url="http://localhost:8001",
    username="trader@example.com",
    password="SecurePassword123!",
    persist_session=True  # Get 30-day refresh token
)

# Method 2: Two-step
client = TradingClient(
    api_url="http://localhost:8081",
    user_service_url="http://localhost:8001"
)
client.login("trader@example.com", "SecurePassword123!")

# Auto-refresh happens transparently
inst = client.Instrument("NIFTY50")
print(inst['5m'].close)  # Tokens auto-refreshed if needed

# Cleanup
client.logout()  # Calls user_service logout endpoint
```

#### API Key Authentication (Server-to-Server)

**Architecture:**
```
SDK + API Key                    Backend API
    │                               │
    ├─ GET /api/endpoint ──────────>│
    │  (Bearer: api_key)            │
    │                               │ Validate API key
    │                               │ Check permissions
    │                               │ Check rate limits
    │<──────────── Response with data│
```

**Implementation:**

```python
# Simple initialization
client = TradingClient(
    api_url="http://localhost:8081",
    api_key="sb_30d4d5ea_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6"
)

# Use immediately - no login needed
inst = client.Instrument("NIFTY50")
account = client.Account()
```

### User Service Integration Points

**`user_service` Endpoints Called:**

1. **`POST /v1/auth/login`** - User authentication
   - Request: `{email, password, persist_session}`
   - Response: `{access_token, refresh_token, expires_in, user}`

2. **`POST /v1/auth/refresh`** - Token refresh
   - Request: `refresh_token` (in cookie)
   - Response: `{access_token, expires_in}`

3. **`POST /v1/auth/logout`** - Session cleanup
   - Request: `Authorization: Bearer {access_token}`
   - Response: `{status: "ok"}`

4. **`GET /v1/auth/.well-known/jwks.json`** - JWKS keys (cached by backend)
   - Used by backend to verify JWT signatures

### Security Features

**JWT Security:**
- Short-lived access tokens (15 minutes)
- Long-lived refresh tokens (30 days)
- RS256 signature verification
- Issuer/audience validation
- Automatic token rotation
- Transparent refresh (no developer action needed)

**API Key Security:**
- SHA-256 hashed in database
- IP whitelisting
- Rate limiting per key
- Per-key permission control
- Account restrictions
- Audit trail via logs
- Explicit revocation

---

## 3. Client Initialization Options

### TradingClient Constructor

```python
class TradingClient:
    def __init__(
        self,
        api_url: str,                          # Required: Backend URL
        api_key: Optional[str] = None,         # API key for server auth
        user_service_url: Optional[str] = None,  # User service for JWT
        cache: Optional[SimpleCache] = None,   # Custom cache
        enable_disk_cache: bool = True,        # Disk cache for indicators
        cache_dir: Optional[Path] = None,      # Cache directory
        cache_ttl: int = 86400                 # Cache TTL (24h)
    )
```

### Initialization Patterns

**Pattern 1: JWT with from_credentials (Recommended)**
```python
client = TradingClient.from_credentials(
    api_url="http://localhost:8081",
    user_service_url="http://localhost:8001",
    username="trader@example.com",
    password="password",
    persist_session=True  # Get refresh token
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

**Pattern 3: API Key (no login needed)**
```python
client = TradingClient(
    api_url="http://localhost:8081",
    api_key="sb_30d4d5ea_..."
)
```

**Pattern 4: Custom cache and disk persistence**
```python
client = TradingClient(
    api_url="http://localhost:8081",
    api_key="sb_...",
    enable_disk_cache=True,  # Cache indicators to disk
    cache_dir=Path.home() / ".stocksblitz",
    cache_ttl=3600  # 1 hour
)
```

### Available Properties and Methods

```python
# Create instruments
inst = client.Instrument("NIFTY25N0424500PE")

# Access account
account = client.Account()
account2 = client.Account("secondary")  # Multiple accounts

# Create strategies
strategy = client.Strategy(
    strategy_name="RSI Mean Reversion",
    strategy_type="mean_reversion"
)

# Filter instruments
filter = client.InstrumentFilter("NSE@NIFTY@Nw@Put")

# Access services
client.alerts       # AlertService
client.messaging    # MessagingService
client.calendar     # CalendarService
client.news         # NewsService
client.indicators   # IndicatorRegistry

# Lifecycle
client.login(username, password)
client.logout()
client.clear_cache()
```

---

## 4. Support for Different User Types

### User Type 1: Individual Traders (Interactive)

**Characteristics:**
- Login with email/password
- Interactive Jupyter notebooks
- Real-time decision making
- Session persistence

**Recommended Auth:** JWT with `from_credentials()`

```python
# One-line setup for traders
client = TradingClient.from_credentials(
    api_url="http://localhost:8081",
    user_service_url="http://localhost:8001",
    username="trader@example.com",
    password="MyPassword123!",
    persist_session=True  # Session lasts 30 days
)

# Use in notebook
inst = client.Instrument("NIFTY50")
print(inst['5m'].rsi[14])

# Tokens auto-refresh transparently
```

**Capabilities:**
- Full trading operations (buy/sell/cancel)
- Strategy creation and execution
- Real-time indicators and Greeks
- News and market alerts
- Calendar reminders

### User Type 2: Automated Bots (Server)

**Characteristics:**
- Long-running background services
- No user interaction
- 24/7 operation
- Environment-based configuration

**Recommended Auth:** API Key

```python
import os

# Load from environment
API_KEY = os.getenv("STOCKSBLITZ_API_KEY")

client = TradingClient(
    api_url="http://localhost:8081",
    api_key=API_KEY
)

# Run forever
while True:
    inst = client.Instrument("NIFTY50")
    if inst['5m'].rsi[14] > 70:
        client.Account().sell(inst, quantity=50)
    time.sleep(60)
```

**Capabilities:**
- All trading operations
- Strategy execution
- Automated alerts
- Batch data processing

### User Type 3: Institutional Systems (Multi-Account)

**Characteristics:**
- Multiple trading accounts
- Risk management requirements
- Compliance tracking
- API key rotation

**Setup:**
```python
import os

# Different keys for different accounts
primary_key = os.getenv("API_KEY_PRIMARY")
secondary_key = os.getenv("API_KEY_SECONDARY")

# Create separate clients
primary = TradingClient(
    api_url="http://localhost:8081",
    api_key=primary_key
)

secondary = TradingClient(
    api_url="http://localhost:8081",
    api_key=secondary_key
)

# Multi-account operations
primary_account = primary.Account("primary")
secondary_account = secondary.Account("secondary")

# Execution with isolation
with primary.Strategy(strategy_name="Portfolio A") as strat_a:
    inst = primary.Instrument("NIFTY50")
    strat_a.buy(inst, quantity=10)

with secondary.Strategy(strategy_name="Portfolio B") as strat_b:
    inst = secondary.Instrument("BANKNIFTY")
    strat_b.buy(inst, quantity=5)
```

### User Type 4: Data Scientists (Analysis Only)

**Characteristics:**
- Read-only access
- No trading operations
- Bulk data download
- Backtesting

**Note:** Current SDK doesn't have explicit read-only mode, but can be restricted by:
1. Creating API keys with no `can_trade` permission
2. Using JWT accounts without trading privileges

```python
# Create read-only API key via backend
# POST /api/keys/create with permissions: {can_read: true, can_trade: false}

client = TradingClient(
    api_url="http://localhost:8081",
    api_key="sb_readonly_..."
)

# Data access only
inst = client.Instrument("NIFTY50")
ohlc = inst['5m'][0:100]  # Get 100 candles
rsi_values = [candle.rsi[14] for candle in ohlc]

# This would fail:
# account.buy(inst, 50)  # Permission denied
```

### User Type 5: Integration Partners

**Characteristics:**
- Third-party integrations
- Service-to-service communication
- OAuth-style flow (future)
- Scoped permissions

**Current:** API key with specific permissions

```python
# Third-party gets scoped API key
PARTNER_KEY = "sb_partner_integration_..."

client = TradingClient(
    api_url="http://localhost:8081",
    api_key=PARTNER_KEY
)

# Can perform only allowed operations
# Example: Only access specific accounts
account = client.Account("partner_trading_account")
```

---

## 5. SDK Components Deep Dive

### A. Core Trading Classes

**Instrument Class** (instrument.py)
```python
inst = client.Instrument("NIFTY25N0424500PE")

# Properties
inst.ltp            # Last traded price
inst.volume         # Trading volume
inst.oi             # Open interest
inst.bid/inst.ask   # Bid/ask prices

# Greeks (for options)
inst.delta          # Price sensitivity
inst.gamma          # Delta acceleration
inst.theta          # Time decay
inst.vega           # Volatility sensitivity
inst.iv             # Implied volatility

# Timeframe access
inst['5m']          # 5-minute candles
inst['1h']          # 1-hour candles
inst['1d']          # Daily candles

# Indicators on current candle
inst['5m'].rsi[14]  # RSI(14)
inst['5m'].sma[20]  # SMA(20)
inst['5m'].macd[12,26,9]  # MACD
```

**Account Class** (account.py)
```python
account = client.Account()

# Properties
account.positions   # List[Position]
account.holdings    # List[Dict]
account.orders      # List[Order]
account.funds       # Funds object

# Methods
account.position("NIFTY50")  # Get specific
account.buy(inst, qty=50)     # Market order
account.sell(inst, qty=50, order_type="LIMIT", price=100)
```

**Strategy Class** (strategy.py)
```python
strategy = client.Strategy(
    strategy_name="RSI Mean Reversion",
    strategy_type=StrategyType.MEAN_REVERSION
)

# Context manager
with strategy:
    inst = client.Instrument("NIFTY50")
    if inst['5m'].rsi[14] < 30:
        strategy.buy(inst, quantity=50)  # Linked to strategy

# Metrics
metrics = strategy.metrics
print(f"P&L: ₹{metrics.total_pnl:,.2f}")
print(f"ROI: {metrics.roi:.2f}%")
print(f"Trades: {metrics.total_trades}")
```

**Supported Indicators** (40+)
```
Momentum:     RSI, STOCH, STOCHRSI, MACD, CCI, MOM, ROC, TSI, WILLR, AO, PPO
Trend:        SMA, EMA, WMA, HMA, DEMA, TEMA, VWMA, ZLEMA, KAMA, T3
Volatility:   ATR, NATR, BBANDS, KC, DC
Volume:       OBV, AD, ADX, VWAP, MFI
Other:        PSAR, SUPERTREND, AROON, FISHER
```

### B. Advanced Features

**InstrumentFilter** - Pattern-based searching
```python
# Pattern: Exchange@Underlying@Expiry@OptionType[@Strike]
filter = client.InstrumentFilter("NSE@NIFTY@Nw@Put")

# Lambda filtering
results = filter.where(lambda i: i.ltp > 50 and i.oi > 100000)

# Criteria-based
results = filter.find(ltp_min=50, ltp_max=100)

# Option selection
atm = filter.atm()      # At-the-money
otm2 = filter.otm(2)    # 2 strikes OTM
itm1 = filter.itm(1)    # 1 strike ITM

# Top by attribute
top_oi = filter.top(5, by='oi')
```

**IndicatorRegistry** - Validation and caching
```python
# List available indicators
indicators = client.indicators.list_indicators()
momentum = client.indicators.list_indicators(category="momentum")

# Validate parameters
is_valid, error = client.indicators.validate_indicator(
    "RSI",
    {"length": 14, "scalar": 100}
)

# Clear cache after custom indicators added
client.indicators.clear_cache()
```

### C. Services Layer

**AlertService** - Event-based alerts
```python
def on_alert(event):
    print(f"Alert: {event.message}")

client.alerts.on(AlertType.PRICE, on_alert)

alert = client.alerts.raise_alert(
    alert_type=AlertType.PRICE,
    priority=AlertPriority.HIGH,
    symbol="NIFTY50",
    message="Price crossed 24000"
)
```

**MessagingService** - Pub/sub communication
```python
def on_signal(msg):
    print(f"Signal: {msg.content}")

client.messaging.subscribe("trade-signals", on_signal)

client.messaging.publish(
    topic="trade-signals",
    content={"symbol": "NIFTY50", "action": "BUY"}
)
```

**CalendarService** - Reminders and scheduling
```python
from datetime import datetime, timedelta

reminder_id = client.calendar.set_reminder(
    title="Close positions",
    scheduled_at=datetime.now() + timedelta(hours=1),
    callback=lambda r: print("Close positions now!")
)

client.calendar.start_monitoring()
```

**NewsService** - Sentiment analysis
```python
def on_news(item):
    if item.sentiment == NewsSentiment.NEGATIVE:
        print(f"Negative news: {item.title}")

client.news.subscribe(
    callback=on_news,
    category=NewsCategory.MARKET,
    symbols=["NIFTY50"]
)

summary = client.news.get_sentiment_summary(["NIFTY50"], hours=24)
```

---

## 6. Data Models and Type Safety

### Enumerations (17 enum classes)
```python
DataState          # VALID, STALE, NO_DATA, NOT_SUBSCRIBED, ERROR, UNAVAILABLE
Exchange           # NSE, BSE, NFO, BFO, CDS, MCX
TransactionType    # BUY, SELL
OrderType          # MARKET, LIMIT, SL, SL-M
ProductType        # CNC, MIS, NRML
Validity           # DAY, IOC, TTL
OrderStatus        # PENDING, OPEN, COMPLETE, CANCELLED, REJECTED, MODIFIED
PositionType       # LONG, SHORT
Timeframe          # 1min, 5min, 15min, 30min, 1hour, 1day
AlertType          # PRICE, VOLUME, INDICATOR, ORDER, POSITION, MARGIN
AlertPriority      # LOW, MEDIUM, HIGH, CRITICAL
MessageType        # SIGNAL, NOTIFICATION, DATA, CONTROL
ReminderFrequency  # ONCE, DAILY, WEEKLY, MONTHLY
NewsCategory       # MARKET, STOCKS, OPTIONS, FUTURES, CRYPTO, MACRO
NewsSentiment      # POSITIVE, NEGATIVE, NEUTRAL, MIXED
StrategyType       # MEAN_REVERSION, MOMENTUM, ARBITRAGE, CUSTOM
StrategyStatus     # ACTIVE, PAUSED, COMPLETED, FAILED
EventStatus        # TRIGGERED, ACKNOWLEDGED, DISMISSED, EXPIRED
```

### Dataclasses (8+ models)
```python
AlertEvent          # alert_id, type, priority, message, data, timestamps
Message             # message_id, type, content, sender, metadata
Reminder            # reminder_id, title, frequency, schedule, callback
NewsItem            # news_id, category, title, sentiment, sentiment_score
OrderRequest        # tradingsymbol, transaction_type, quantity, order_type
QuoteData           # symbol, ltp, volume, oi, bid/ask
GreeksData          # delta, gamma, theta, vega, iv, rho, intrinsic/extrinsic
MarketDepth         # buy_levels, sell_levels, spread, imbalance
LiquidityMetrics    # score, tier, spread, depth, market impact
FuturesPosition     # signal, strength, sentiment, price/oi changes
RolloverMetrics     # pressure, oi_pct, days_to_expiry
StrategyMetrics     # pnl, roi, trades, sharpe_ratio, max_drawdown
```

### Exception Hierarchy
```
StocksBlitzError (base)
├── APIError
├── AuthenticationError
├── InstrumentNotFoundError
├── InsufficientFundsError
├── InvalidOrderError
├── CacheError
├── DataUnavailableError
├── StaleDataError
├── InstrumentNotSubscribedError
├── IndicatorUnavailableError
└── DataValidationError
```

---

## 7. Caching Strategy

### Multi-Level Caching

**In-Memory Cache (SimpleCache)**
- Default TTL: 60 seconds
- Stores frequently accessed data
- Cleared on `client.clear_cache()`

**Disk Cache (IndicatorRegistry)**
- Location: `~/.stocksblitz/` (configurable)
- Default TTL: 24 hours
- Persists indicator definitions across sessions
- Enabled by default, can be disabled

**API Call Caching**
```python
# Automatic caching based on TTL
result = client._api.get(
    "/instruments/current",
    cache_ttl=300  # Cache for 5 minutes
)

# No caching
result = client._api.get(
    "/live-price",
    cache_ttl=None  # No caching
)
```

---

## 8. Production Readiness

### Version Information
- **Current Version:** 0.2.0 (v0.2 Release)
- **Python Support:** 3.8, 3.9, 3.10, 3.11, 3.12
- **Dependencies:** Only `httpx>=0.25.0` (HTTP client)

### Capabilities Checklist

**Core Trading:**
- ✅ Multiple authentication methods
- ✅ 40+ technical indicators
- ✅ Multi-timeframe analysis
- ✅ Options Greeks calculation
- ✅ Order management (place, cancel, modify)
- ✅ Position tracking
- ✅ Strategy isolation
- ✅ Multi-account support

**Advanced Features:**
- ✅ Instrument filtering with patterns
- ✅ Real-time alerts
- ✅ Pub/sub messaging
- ✅ Calendar/reminders
- ✅ News aggregation with sentiment
- ✅ Indicator registry validation
- ✅ Custom indicator support
- ✅ Session persistence (JWT refresh)

**Enterprise Features:**
- ✅ Type hints and IDE autocomplete
- ✅ Comprehensive error handling
- ✅ Caching (in-memory + disk)
- ✅ Rate limiting support
- ✅ IP whitelisting (API keys)
- ✅ Permission-based access control
- ✅ Audit trail support
- ✅ Full documentation

### Roadmap (v0.3.0+)

Planned features:
- WebSocket streaming support
- Strategy backtesting framework
- Performance analytics dashboard
- Advanced risk management tools
- Portfolio optimization
- Redis caching backend

---

## 9. Key Files Reference

| File | Purpose | LOC |
|------|---------|-----|
| `client.py` | Main TradingClient class | ~550 |
| `api.py` | HTTP client + authentication | ~350 |
| `instrument.py` | Instrument + Candle + indicators | ~1,000 |
| `account.py` | Account + Position + Order | ~400 |
| `strategy.py` | Strategy management + metrics | ~400 |
| `filter.py` | Instrument filtering | ~350 |
| `indicators.py` | Indicator computation | ~200 |
| `services/` | 4 service modules | ~600 |
| `types.py` | Type definitions | ~250 |
| `enums.py` | Enumeration classes | ~200 |
| `cache.py` | Caching implementation | ~100 |
| `exceptions.py` | Exception classes | ~50 |

---

## 10. Usage Examples

### Quick Start (JWT)
```python
from stocksblitz import TradingClient

client = TradingClient.from_credentials(
    api_url="http://localhost:8081",
    user_service_url="http://localhost:8001",
    username="trader@example.com",
    password="password"
)

inst = client.Instrument("NIFTY50")
if inst['5m'].rsi[14] < 30:
    client.Account().buy(inst, quantity=50)
```

### Quick Start (API Key)
```python
from stocksblitz import TradingClient
import os

client = TradingClient(
    api_url="http://localhost:8081",
    api_key=os.getenv("STOCKSBLITZ_API_KEY")
)

account = client.Account()
positions = account.positions
for pos in positions:
    print(f"{pos.tradingsymbol}: P&L={pos.pnl_percent:.2f}%")
```

### Strategy Example
```python
strategy = client.Strategy(
    strategy_name="RSI Mean Reversion",
    strategy_type="mean_reversion"
)

with strategy:
    inst = client.Instrument("NIFTY25N0424500PE")
    
    if inst['5m'].rsi[14] < 30:
        strategy.buy(inst, quantity=50)
    
    metrics = strategy.metrics
    print(f"ROI: {metrics.roi:.2f}%")
```

---

## 11. Conclusion

The StocksBlitz Python SDK is a **production-ready, enterprise-grade** trading platform with:

1. **Flexible Authentication:** Both JWT (users) and API keys (services)
2. **Rich Feature Set:** 40+ indicators, strategies, alerts, messaging
3. **Type Safety:** Full type hints and IDE autocomplete
4. **Ease of Use:** Pythonic API with lazy evaluation
5. **Scalability:** Multi-account, multi-strategy support
6. **Security:** Encrypted tokens, rate limiting, IP whitelisting
7. **Maintainability:** Clean architecture, comprehensive documentation

**Best For:**
- Individual traders (Jupyter notebooks)
- Algorithmic trading bots
- Quantitative analysis platforms
- Fintech integrations
- Multi-asset portfolio management

