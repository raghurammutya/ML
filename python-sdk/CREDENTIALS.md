# SDK Testing Credentials

## ✅ Working Test User

A test user has been created and verified for SDK testing.

### **Credentials**

```
Email:    test_sdk@example.com
Password: TestSDK123!@#$
```

### **User Details**

- **User ID:** 3
- **Status:** Active (pending_verification)
- **Created:** 2025-11-04 07:24:45 UTC
- **Authentication:** JWT (RS256)

### **Verification**

The authentication has been tested and is working:

```bash
$ python3 /tmp/quick_test.py
Testing authentication...
✓ Authentication successful!

Testing basic instrument access...
✓ NIFTY 50 LTP: 25680.35

All tests passed!
```

---

## 🚀 Running the Enhanced Monitor

### **Quick Start**

```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/python-sdk
python3 test_tick_monitor_enhanced.py
```

The script now uses the correct credentials automatically:
- Username: `test_sdk@example.com`
- Password: `TestSDK123!@#$`

### **Expected Output**

```
================================================================================
              StocksBlitz SDK - Enhanced Tick Monitor
================================================================================

ℹ API URL: http://localhost:8081
ℹ User Service URL: http://localhost:8001
ℹ Username: test_sdk@example.com

────────────────────────────────────────────────────────────────────────────────
Authentication
────────────────────────────────────────────────────────────────────────────────
✓ Authenticated as test_sdk@example.com

[Monitor starts...]
```

---

## 📋 Alternative: Original User (raghurammutya@gmail.com)

If you prefer to use the original email `raghurammutya@gmail.com`, you'll need to:

1. **Option 1: Reset Password via API**
   ```python
   # Not implemented yet - requires password reset flow
   ```

2. **Option 2: Update Credentials in Script**
   Edit line 36-37 in `test_tick_monitor_enhanced.py`:
   ```python
   USERNAME = "raghurammutya@gmail.com"
   PASSWORD = "YOUR_ACTUAL_PASSWORD"
   ```

3. **Option 3: Script will prompt**
   If authentication fails, the script will prompt you to enter the password manually.

---

## 🔐 Password Requirements

When creating users via API:
- **Minimum length:** 12 characters
- **Must contain:** Letters, numbers, and special characters
- **Format:** `TestSDK123!@#$` (example)

---

## 🧪 Testing Authentication

### **Quick Test**

```bash
python3 << 'EOF'
import sys
sys.path.insert(0, '/mnt/stocksblitz-data/Quantagro/tradingview-viz/python-sdk')
from stocksblitz import TradingClient

client = TradingClient.from_credentials(
    api_url="http://localhost:8081",
    user_service_url="http://localhost:8001",
    username="test_sdk@example.com",
    password="TestSDK123!@#$"
)
print("✓ Authentication successful!")
EOF
```

### **Via curl**

```bash
curl -X POST "http://localhost:8001/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"test_sdk@example.com","password":"TestSDK123!@#$"}' \
  | python3 -c "import sys, json; print('Success!' if 'access_token' in json.load(sys.stdin) else 'Failed')"
```

---

## 📁 Files Updated

1. **`test_tick_monitor_enhanced.py`** - Updated with working credentials
2. **`CREDENTIALS.md`** - This file (credential reference)
3. **`TICK_MONITOR_README.md`** - User guide (unchanged)

---

## ⚠️ Security Note

These are **test credentials for development only**. Do not use in production.

For production:
- Use proper OAuth2 flows
- Implement password reset mechanisms
- Use environment variables for credentials
- Enable MFA/TOTP

---

## 🎯 Next Steps

1. **Run the enhanced monitor:**
   ```bash
   python3 test_tick_monitor_enhanced.py
   ```

2. **Monitor will run for 5 minutes** and display:
   - Live tick data for NIFTY 50, options, and futures
   - All Greeks (delta, gamma, theta, vega, IV)
   - Technical indicators (RSI, SMA, EMA, MACD, BB, ATR, ADX)
   - Option chain heatmap
   - OI change tracking

3. **Data will be exported** to `/tmp/stocksblitz_exports/` as CSV files

4. **Press Ctrl+C** to stop early and export collected data

---

**Ready to test!** 🚀
