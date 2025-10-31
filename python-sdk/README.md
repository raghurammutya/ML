# StocksBlitz Python SDK

**Intuitive Python interface for algorithmic trading with the StocksBlitz platform.**

## Features

- ✅ **Pythonic syntax** - Read like natural language
- ✅ **Lazy evaluation** - Only fetch data when needed
- ✅ **Smart caching** - Minimize API calls
- ✅ **40+ technical indicators** - RSI, MACD, SMA, EMA, Bollinger Bands, ATR, and more
- ✅ **Multi-timeframe analysis** - 1m, 5m, 15m, 1h, 1d
- ✅ **Trading operations** - Place orders, manage positions, track PnL
- ✅ **Strategy management** - Isolated P&L tracking, metrics, and performance analysis (v0.2.0)
- ✅ **Instrument filtering** - Pattern-based filtering with ATM/OTM/ITM selection (v0.2.0)
- ✅ **Advanced services** - Alerts, messaging, calendar, and news integration (v0.2.0)
- ✅ **Type hints** - Full IDE autocomplete support with enums and dataclasses

## Installation

```bash
pip install stocksblitz
```

Or install from source:

```bash
git clone https://github.com/raghurammutya/ML.git
cd ML/python-sdk
pip install -e .
```

## Quick Start

```python
from stocksblitz import TradingClient

# Initialize client
client = TradingClient(
    api_url="http://localhost:8009",
    api_key="YOUR_API_KEY"
)

# Create instrument
inst = client.Instrument("NIFTY25N0424500PE")

# Check RSI
if inst['5m'].rsi[14] > 70:
    print("Overbought!")

# Access OHLCV data
current_close = inst['5m'].close
previous_close = inst['5m'][1].close

# Place order
account = client.Account()
if inst.ltp < 50:
    account.buy(inst, quantity=50)
```

## Examples

### 1. Technical Indicators

```python
from stocksblitz import TradingClient

client = TradingClient(api_url="http://localhost:8009", api_key="YOUR_API_KEY")
inst = client.Instrument("NIFTY25N0424500PE")

# RSI
rsi = inst['5m'].rsi[14]
print(f"RSI: {rsi}")

# Moving Averages
sma_20 = inst['5m'].sma[20]
ema_50 = inst['5m'].ema[50]

if sma_20 > ema_50:
    print("Bullish crossover")

# MACD
macd = inst['5m'].macd[12, 26, 9]
print(f"MACD: {macd}")  # Returns dict with 'macd', 'signal', 'histogram'

# Bollinger Bands
bb = inst['5m'].bbands[20, 2]
if inst.ltp > bb['upper']:
    print("Price above upper band")

# ATR (Volatility)
atr = inst['5m'].atr[14]
print(f"ATR: {atr}")
```

### 2. Multi-Timeframe Analysis

```python
# Check RSI across multiple timeframes
rsi_1m = inst['1m'].rsi[14]
rsi_5m = inst['5m'].rsi[14]
rsi_15m = inst['15m'].rsi[14]
rsi_1h = inst['1h'].rsi[14]

if all(rsi > 60 for rsi in [rsi_1m, rsi_5m, rsi_15m, rsi_1h]):
    print("Bullish across all timeframes!")
```

### 3. OHLCV Data Access

```python
# Current candle
candle = inst['5m'][0]
print(f"OHLC: {candle.open}, {candle.high}, {candle.low}, {candle.close}")

# Historical candles
prev_candle = inst['5m'][3]  # 3 candles ago
print(f"Close 3 candles ago: {prev_candle.close}")

# Shortcut for current candle
current_close = inst['5m'].close  # Same as inst['5m'][0].close
current_high = inst['5m'].high
```

### 4. Trading Operations

```python
account = client.Account()

# Get account info
funds = account.funds
print(f"Available cash: {funds.available_cash}")

# Get positions
positions = account.positions
for pos in positions:
    print(f"{pos.tradingsymbol}: PnL={pos.pnl} ({pos.pnl_percent:.2f}%)")

# Place orders
inst = client.Instrument("NIFTY25N0424500PE")

# Market order
account.buy(inst, quantity=50)

# Limit order
account.buy(inst, quantity=50, order_type="LIMIT", price=100)

# Stop loss order
account.sell(inst, quantity=50, order_type="SL", trigger_price=95, price=95)
```

### 5. Position Management

```python
account = client.Account()

# Get specific position
pos = account.position("NIFTY25N0424500PE")

if pos:
    print(f"Quantity: {pos.quantity}")
    print(f"PnL: {pos.pnl} ({pos.pnl_percent:.2f}%)")

    # Close position
    if pos.pnl_percent > 10:
        pos.close()  # Take profit

    # Stop loss
    if pos.pnl_percent < -5:
        pos.close()  # Stop loss
```

### 6. Option Greeks

```python
inst = client.Instrument("NIFTY25N0424500PE")

# Access Greeks
delta = inst.delta
gamma = inst.gamma
theta = inst.theta
vega = inst.vega
iv = inst.iv  # Implied volatility

# Greeks-based strategy
if inst.delta > 0.5 and inst.theta < -5 and inst.iv < 20:
    account.buy(inst, quantity=50)
```

### 7. Complete Trading Strategy

```python
#!/usr/bin/env python3
"""
RSI Mean Reversion Strategy
"""

from stocksblitz import TradingClient
import time

# Initialize
client = TradingClient(
    api_url="http://localhost:8009",
    api_key="YOUR_API_KEY"
)

inst = client.Instrument("NIFTY25N0424500PE")
account = client.Account()

def run_strategy():
    """Execute strategy logic."""

    # Get RSI
    rsi = inst['5m'].rsi[14]

    # Check existing position
    pos = account.position(inst)

    # Entry signal
    if rsi < 30 and pos is None:
        print(f"BUY: RSI={rsi:.2f} (oversold)")
        account.buy(inst, quantity=50)

    # Exit signal
    if rsi > 70 and pos is not None:
        print(f"SELL: RSI={rsi:.2f} (overbought)")
        pos.close()

    # Stop loss
    if pos and pos.pnl_percent < -5:
        print(f"STOP LOSS: PnL={pos.pnl_percent:.2f}%")
        pos.close()

    # Take profit
    if pos and pos.pnl_percent > 10:
        print(f"TAKE PROFIT: PnL={pos.pnl_percent:.2f}%")
        pos.close()

# Run every 5 minutes
while True:
    try:
        run_strategy()
    except Exception as e:
        print(f"Error: {e}")

    time.sleep(300)  # 5 minutes
```

### 8. Strategy Management (v0.2.0)

```python
from stocksblitz import TradingClient, StrategyType

client = TradingClient(api_url="http://localhost:8009", api_key="YOUR_API_KEY")

# Create strategy
strategy = client.Strategy(
    strategy_name="RSI Mean Reversion",
    strategy_type=StrategyType.MEAN_REVERSION,
    config={"rsi_oversold": 30, "rsi_overbought": 70}
)

# Use context manager
with strategy:
    inst = client.Instrument("NIFTY25N0424500PE")

    # Check RSI
    if inst['5m'].rsi[14] < 30:
        strategy.buy(inst, quantity=50)  # Auto-linked to strategy

    # Get strategy metrics
    metrics = strategy.metrics
    print(f"P&L: ₹{metrics.total_pnl:,.2f}")
    print(f"ROI: {metrics.roi:.2f}%")
    print(f"Trades: {metrics.total_trades}")

# Get strategy positions
for pos in strategy.positions:
    print(f"{pos.tradingsymbol}: P&L=₹{pos.pnl:,.2f}")
```

### 9. Instrument Filtering (v0.2.0)

```python
from stocksblitz import TradingClient

client = TradingClient(api_url="http://localhost:8009", api_key="YOUR_API_KEY")

# Pattern-based filtering
filter = client.InstrumentFilter("NSE@NIFTY@28-Oct-2025@Put")

# Lambda filtering
liquid_options = filter.where(lambda i: (
    50 < i.ltp < 100 and
    i.oi > 100000 and
    i.delta > 0.3
))

# Criteria-based filtering
results = filter.find(ltp_min=50, ltp_max=100, oi_min=100000)

# ATM/OTM/ITM selection
filter = client.InstrumentFilter("NSE@NIFTY@Nw@Put")  # Next week
atm = filter.atm()  # At-the-money
otm2 = filter.otm(2)  # 2 strikes out-of-the-money

# Top by attribute
top_oi = filter.top(5, by='oi')  # Top 5 by open interest

# Filter by indicators
oversold = filter.where(lambda i: i['5m'].rsi[14] < 30)
```

### 10. Advanced Services (v0.2.0)

```python
from stocksblitz import TradingClient, AlertType, AlertPriority, NewsCategory, NewsSentiment

client = TradingClient(api_url="http://localhost:8009", api_key="YOUR_API_KEY")

# Alerts
def on_price_alert(event):
    print(f"Alert: {event.message}")
    # Take action based on alert

client.alerts.on(AlertType.PRICE, on_price_alert)

alert = client.alerts.raise_alert(
    alert_type=AlertType.PRICE,
    priority=AlertPriority.HIGH,
    symbol="NIFTY50",
    message="Price crossed 24000"
)

# Messaging (Pub/Sub)
def on_signal(msg):
    print(f"Signal received: {msg.content}")

client.messaging.subscribe("trade-signals", on_signal)

client.messaging.publish(
    topic="trade-signals",
    content={"symbol": "NIFTY50", "action": "BUY"}
)

# Calendar & Reminders
from datetime import datetime, timedelta

reminder_id = client.calendar.set_reminder(
    title="Close positions",
    scheduled_at=datetime.now() + timedelta(hours=1),
    callback=lambda r: print("Time to close positions!")
)

client.calendar.start_monitoring()

# News with Sentiment
def on_news(item):
    if item.sentiment == NewsSentiment.NEGATIVE:
        print(f"Negative news: {item.title}")

client.news.subscribe(
    callback=on_news,
    category=NewsCategory.MARKET,
    symbols=["NIFTY50"]
)

# Get sentiment summary
summary = client.news.get_sentiment_summary(["NIFTY50"], hours=24)
```

## API Reference

### TradingClient

Main entry point for the SDK.

```python
client = TradingClient(api_url: str, api_key: str)
```

**Methods**:
- `Instrument(spec: str) -> Instrument` - Create instrument
- `Account(account_id: str = "primary") -> Account` - Create account instance
- `InstrumentFilter(pattern: str) -> InstrumentFilter` - Create filter (v0.2.0)
- `Strategy(**kwargs) -> Strategy` - Create or load strategy (v0.2.0)
- `clear_cache()` - Clear all cached data

**Services** (v0.2.0):
- `alerts: AlertService` - Event-based alert system
- `messaging: MessagingService` - Pub/sub messaging
- `calendar: CalendarService` - Reminders and scheduling
- `news: NewsService` - News aggregation with sentiment analysis

### Instrument

Represents a tradable instrument.

**Properties**:
- `ltp: float` - Last traded price
- `volume: int` - Volume
- `oi: int` - Open interest
- `delta: float` - Option delta
- `gamma: float` - Option gamma
- `theta: float` - Option theta
- `vega: float` - Option vega
- `iv: float` - Implied volatility

**Methods**:
- `[timeframe: str] -> TimeframeProxy` - Access timeframe data

### TimeframeProxy

Proxy for timeframe-specific data access.

**Methods**:
- `[offset: int] -> Candle` - Access candle N candles back

**Properties** (delegated to current candle):
- `open`, `high`, `low`, `close`, `volume` - OHLCV data
- `rsi`, `sma`, `ema`, `macd`, etc. - Indicators

### Candle

Represents a single OHLCV candle.

**Properties**:
- `open: float` - Open price
- `high: float` - High price
- `low: float` - Low price
- `close: float` - Close price
- `volume: int` - Volume
- `time: datetime` - Candle timestamp

**Indicators** (accessed as attributes):
- `rsi[length]` - RSI
- `sma[length]` - Simple Moving Average
- `ema[length]` - Exponential Moving Average
- `macd[fast, slow, signal]` - MACD
- `bbands[length, std]` - Bollinger Bands
- `atr[length]` - Average True Range
- And 30+ more indicators...

### Account

Trading account operations.

**Properties**:
- `positions: List[Position]` - All positions
- `holdings: List[Dict]` - All holdings
- `orders: List[Order]` - All orders
- `funds: Funds` - Available funds

**Methods**:
- `position(symbol) -> Optional[Position]` - Get specific position
- `buy(instrument, quantity, **kwargs) -> Order` - Place buy order
- `sell(instrument, quantity, **kwargs) -> Order` - Place sell order

### Position

Represents an open position.

**Properties**:
- `tradingsymbol: str` - Trading symbol
- `quantity: int` - Position quantity
- `average_price: float` - Average entry price
- `last_price: float` - Current price
- `pnl: float` - Unrealized PnL
- `pnl_percent: float` - PnL percentage
- `is_long: bool` - Check if long position
- `is_short: bool` - Check if short position

**Methods**:
- `close(**kwargs) -> Order` - Close position
- `history(lookback: int) -> List[PositionSnapshot]` - Get position history

### Funds

Account funds information.

**Properties**:
- `available_cash: float` - Available cash
- `used_margin: float` - Margin in use
- `available_margin: float` - Available margin
- `total_margin: float` - Total margin

## Supported Indicators

- **Momentum**: RSI, STOCH, STOCHRSI, MACD, CCI, MOM, ROC, TSI, WILLR, AO, PPO
- **Trend**: SMA, EMA, WMA, HMA, DEMA, TEMA, VWMA, ZLEMA, KAMA, T3
- **Volatility**: ATR, NATR, BBANDS, KC, DC
- **Volume**: OBV, AD, ADX, VWAP, MFI
- **Other**: PSAR, SUPERTREND, AROON, FISHER

## Error Handling

```python
from stocksblitz import (
    InstrumentNotFoundError,
    InsufficientFundsError,
    InvalidOrderError,
    APIError
)

try:
    inst = client.Instrument("INVALID_SYMBOL")
except InstrumentNotFoundError as e:
    print(f"Instrument not found: {e}")

try:
    account.buy(inst, quantity=10000)
except InsufficientFundsError as e:
    print(f"Not enough funds: {e}")

try:
    rsi = inst['5m'].rsi[14]
except APIError as e:
    print(f"API error: {e}")
```

## Development

```bash
# Clone repository
git clone https://github.com/raghurammutya/ML.git
cd ML/python-sdk

# Install development dependencies
pip install -e .[dev]

# Run tests
pytest

# Format code
black stocksblitz/

# Type checking
mypy stocksblitz/
```

## License

MIT License

## Support

For issues and questions:
- GitHub Issues: https://github.com/raghurammutya/ML/issues
- Email: support@stocksblitz.com

## Changelog

### v0.2.0 (2025-10-31)

**Major enhancements**:
- ✅ **Strategy Management**: Create/load strategies with isolated P&L tracking
  - Strategy-specific orders, positions, and holdings
  - Performance metrics (ROI, Sharpe ratio, max drawdown)
  - Context manager support for clean strategy execution
  - Historical snapshots for performance analysis
- ✅ **Instrument Filtering**: Powerful pattern-based instrument search
  - Pattern syntax: `Exchange@Underlying@Expiry@OptionType[@Strike]`
  - Lambda filtering: `filter.where(lambda i: i.ltp > 50)`
  - Criteria-based: `filter.find(ltp_min=50, oi_min=100000)`
  - ATM/OTM/ITM selection for options
  - Relative notation support (Nw=next week, Nm=next month)
- ✅ **Advanced Services**:
  - **Alerts**: Event-based alert system with priority levels
  - **Messaging**: Pub/sub messaging for inter-strategy communication
  - **Calendar**: Set recurring/one-time reminders with callbacks
  - **News**: Aggregation with ML sentiment analysis
- ✅ **Type Safety**: 17 enum classes and 7 dataclass models
- ✅ **Enhanced Exception Handling**: Comprehensive error types

### v0.1.0 (2025-10-31)

**Initial release**:
- Core instrument classes
- 40+ technical indicators
- Trading operations
- Position management
- Smart caching
- Type hints

## Roadmap

**v0.3.0** (Planned):
- WebSocket streaming support
- Strategy backtesting framework
- Performance analytics
- Risk management tools
- Portfolio optimization
- Redis caching backend

---

**Made with ❤️ for algorithmic traders**
