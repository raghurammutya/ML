# Enhanced Tick Monitor - User Guide

## Overview

The **Enhanced Tick Monitor** is a comprehensive testing tool for the StocksBlitz Python SDK that demonstrates all features including real-time tick data, Greeks, technical indicators, futures monitoring, and data export.

---

## 🚀 Quick Start

### 1. Prerequisites

- Backend service running on port `8081`
- User service running on port `8001`
- User account: `raghurammutya@gmail.com` exists

### 2. Password Information

The user `raghurammutya@gmail.com` exists in the database (created on 2025-07-11).

**Default test password:** `SecurePass123!`

If this doesn't work, the script will prompt you to enter the password manually.

### 3. Run the Monitor

```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/python-sdk
python3 test_tick_monitor_enhanced.py
```

---

## 📊 Features

### ✅ Real-Time Data Monitoring

**Underlying (NIFTY 50)**
- Last Traded Price (LTP)
- OHLC data (Open, High, Low, Close)
- Volume
- Price change (absolute & percentage)

**Options (14 strikes monitored)**
- 7 CALL options (ITM3 to OTM3)
- 7 PUT options (OTM3 to ITM3)
- Data for each option:
  - LTP, Bid, Ask
  - Volume
  - Open Interest with change tracking
  - Moneyness label (ATM, ITM1, ITM2, OTM1, OTM2, etc.)
  - All Greeks: Delta (Δ), Gamma (γ), Theta (θ), Vega (ν), IV

**Futures (2 contracts)**
- Current month and next month NIFTY futures
- LTP, OHLC data
- Volume and OI with change tracking

### ✅ Technical Indicators

**Trend Indicators**
- RSI(14) - Relative Strength Index
- SMA(20, 50) - Simple Moving Averages
- EMA(12, 26) - Exponential Moving Averages

**Momentum Indicators**
- MACD(12, 26, 9) - Moving Average Convergence Divergence
  - MACD line
  - Signal line
  - Histogram

**Volatility Indicators**
- Bollinger Bands(20, 2) - Upper, Middle, Lower bands
- ATR(14) - Average True Range

**Trend Strength**
- ADX(14) - Average Directional Index

### ✅ Option Chain Heatmap

Visual representation of OI distribution across strikes:
- Color-coded intensity (high OI highlighted)
- Bar chart visualization
- Put-Call Ratio (PCR)
- ATM strike highlighted with ★

### ✅ Data Export to CSV

All data is automatically exported to `/tmp/stocksblitz_exports/` at the end of the session:

**Exported Files:**
1. `underlying_<session>_<timestamp>.csv` - Underlying tick data
2. `options_<session>_<timestamp>.csv` - Options tick data
3. `futures_<session>_<timestamp>.csv` - Futures tick data
4. `greeks_<session>_<timestamp>.csv` - Greeks data
5. `indicators_<session>_<timestamp>.csv` - Technical indicators

---

## 📈 Sample Output

```
================================================================================
                     LIVE TICK MONITOR - Iteration 5
================================================================================
Session: 20251104_123045
Time: 2025-11-04 12:30:45
Elapsed: 25s / 300s

────────────────────────────────────────────────────────────────────────────────
📊 Underlying: NIFTY 50
────────────────────────────────────────────────────────────────────────────────
LTP: 25,674.40 (+12.85 / +0.05%)
O: 25,687.60  H: 25,687.60  L: 25,680.35  C: 25,680.35  Vol: 0
  Indicators (5m):
    RSI(14): 52.34  SMA(20): 25,650.20  EMA(12): 25,665.80
    MACD: 8.45  Signal: 6.20  Hist: 2.25
    BB: Upper: 25,720.50  Mid: 25,680.35  Lower: 25,640.20
    ATR(14): 45.60  ADX(14): 28.50

────────────────────────────────────────────────────────────────────────────────
📈 FUTURES
────────────────────────────────────────────────────────────────────────────────

NIFTY25NOVFUT (Futures)
  LTP: 25,690.25 (+15.40 / +0.06%)
  O: 25,674.85  H: 25,692.00  L: 25,670.00  C: 25,690.25
  Vol: 12,543  OI: 8,456,325 (+125,450, +1.5%)
  Indicators (5m):
    RSI(14): 53.21  SMA(20): 25,655.30  EMA(12): 25,670.15
    MACD: 9.20  Signal: 7.10  Hist: 2.10

────────────────────────────────────────────────────────────────────────────────
📞 CALL Options
────────────────────────────────────────────────────────────────────────────────

NIFTY25N0425600CE [ATM] (Strike: 25600)
  LTP: 84.85  Bid: 84.00  Ask: 85.70
  Vol: 0  OI: 7,762,875 (+125,000, +1.6%)
  Greeks: Δ: 0.5234  γ: 0.0012  θ: -0.0234  ν: 0.1234  IV: 14.56%
  Indicators (5m):
    RSI(14): 45.67  SMA(20): 82.30  EMA(12): 84.10
    MACD: -1.20  Signal: -0.80  Hist: -0.40

────────────────────────────────────────────────────────────────────────────────
🔥 Option Chain Heatmap (OI Intensity)
────────────────────────────────────────────────────────────────────────────────

Strike     Call OI                   Put OI           PCR
---------- --------------- ----- --------------- ----------
25,400      3,245,675  ███████████        ███████████████    8,123,450       2.50
25,450      5,432,100  ███████████        ███████████       7,234,125       1.33
25,500      6,875,250  █████████████      ████████████      6,543,875       0.95
25,550      7,234,100  ██████████████     ██████████        5,432,100       0.75
25,600 ★   7,762,875  ███████████████    ███████████████   6,562,500       0.85
25,650      6,234,500  ████████████       ████████████████  8,123,675       1.30
25,700      4,876,325  █████████          █████████████████ 9,234,125       1.89

Refreshing in 5 seconds... (Data points collected: 45)
```

---

## 🎯 Configuration

You can modify the following parameters in the script:

### Duration
```python
run_tick_monitor(client, duration_seconds=300)  # Run for 5 minutes
```

### Monitored Instruments

**Options:**
```python
monitored_options = [
    f"NIFTY25N04{int(atm_strike - 150)}CE",  # ITM3 Call
    f"NIFTY25N04{int(atm_strike - 100)}CE",  # ITM2 Call
    ...
]
```

**Futures:**
```python
monitored_futures = ["NIFTY25NOVFUT", "NIFTY25DECFUT"]
```

### Export Directory
```python
EXPORT_DIR = Path("/tmp/stocksblitz_exports")
```

---

## 📁 Exported Data Structure

### Options CSV Columns
- timestamp
- symbol
- strike
- option_type
- moneyness
- ltp, bid, ask
- volume, oi
- oi_change, oi_pct_change

### Greeks CSV Columns
- timestamp
- symbol
- delta, gamma, theta, vega, iv

### Indicators CSV Columns
- timestamp
- symbol
- timeframe
- rsi_14, sma_20, sma_50, ema_12, ema_26
- macd, macd_signal, macd_histogram
- bb_upper, bb_middle, bb_lower
- atr_14, adx_14

### Futures CSV Columns
- timestamp
- symbol
- underlying, expiry_code
- ltp, bid, ask
- open, high, low, close
- volume, oi
- oi_change, oi_pct_change
- change, change_pct

---

## 🔍 Troubleshooting

### Authentication Failed

**Error:** `Authentication failed: Invalid credentials`

**Solutions:**
1. The script will prompt for password - enter manually
2. Check if user service is running: `curl http://localhost:8001/health`
3. Verify user exists in database:
   ```sql
   SELECT email, is_active FROM users WHERE email = 'raghurammutya@gmail.com';
   ```

### No Data Available

**Error:** Instruments show "Not found in current snapshot"

**Solutions:**
1. Check if backend is running: `curl http://localhost:8081/health`
2. Check if ticker service is publishing: `redis-cli -p 6379 PUBSUB NUMSUB ticker:nifty:options`
3. Verify market hours (9:15 AM - 3:30 PM IST)

### Missing Indicators

**Issue:** Some indicators show blank

**Explanation:** Indicators require sufficient historical data. During early market hours or for newly subscribed instruments, some indicators may not be available yet.

---

## 🎨 Display Features

### Color Coding

- **Green** - CALL options, positive changes
- **Red** - PUT options, negative changes
- **Yellow** - Moneyness labels, ATM strikes
- **Cyan** - Data labels (Vol, OI, etc.)
- **Magenta** - Greeks display
- **Grey** - Secondary information

### Moneyness Labels

- **ATM** - At The Money (within ±50 of spot)
- **ITM1, ITM2, ITM3** - In The Money (1, 2, 3 strikes)
- **OTM1, OTM2, OTM3** - Out of The Money (1, 2, 3 strikes)

---

## 💡 Tips

1. **Long Sessions:** For sessions longer than 15 minutes, the script will collect substantial data. Monitor disk space in `/tmp/stocksblitz_exports/`

2. **Network Issues:** If you see frequent "Not found" errors, check network connectivity to backend services

3. **Performance:** The script refreshes every 5 seconds. For faster updates, modify the `time.sleep(5)` value

4. **Data Analysis:** Exported CSV files can be imported into Excel, Pandas, or any data analysis tool for further analysis

---

## 📞 Support

For issues or questions:
1. Check backend logs: `docker logs tv-backend`
2. Check ticker service logs: `docker logs tv-ticker`
3. Check user service status: `curl http://localhost:8001/health`

---

**Happy Trading! 🚀**
