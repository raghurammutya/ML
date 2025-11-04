# Indicator Registry API

## Overview

The Indicator Registry API provides a **discovery endpoint** that lists all available technical indicators with their parameters, metadata, and configuration details. This enables the frontend to dynamically generate UI for indicator selection and parameter configuration without hardcoding indicator definitions.

---

## API Endpoints

### 1. List All Indicators

**Endpoint**: `GET /indicators/list`

**Query Parameters**:
- `category` (optional): Filter by category (`momentum`, `trend`, `volatility`, `volume`, `other`)
- `search` (optional): Search query string
- `include_custom` (optional, default=`true`): Include user-defined custom indicators

**Response**:
```json
{
  "status": "success",
  "total": 41,
  "categories": ["momentum", "trend", "volatility", "volume", "other", "custom"],
  "indicators": [
    {
      "name": "RSI",
      "display_name": "Relative Strength Index (RSI)",
      "category": "momentum",
      "description": "Measures the magnitude of recent price changes to evaluate overbought or oversold conditions",
      "parameters": [
        {
          "name": "length",
          "type": "integer",
          "default": 14,
          "min": 2,
          "max": 100,
          "description": "Period length",
          "required": true
        },
        {
          "name": "scalar",
          "type": "integer",
          "default": 100,
          "min": 1,
          "max": 1000,
          "description": "Scaling factor",
          "required": false
        }
      ],
      "outputs": ["RSI"],
      "is_custom": false,
      "author": null,
      "created_at": null
    }
  ]
}
```

**Example Requests**:
```bash
# Get all indicators
curl http://localhost:8081/indicators/list

# Filter by category
curl http://localhost:8081/indicators/list?category=momentum

# Search indicators
curl "http://localhost:8081/indicators/list?search=moving%20average"

# Exclude custom indicators
curl http://localhost:8081/indicators/list?include_custom=false
```

---

### 2. Get Specific Indicator Definition

**Endpoint**: `GET /indicators/definition/{indicator_name}`

**Path Parameters**:
- `indicator_name`: Name of the indicator (e.g., `RSI`, `MACD`, `BBANDS`)

**Response**:
```json
{
  "status": "success",
  "indicator": {
    "name": "MACD",
    "display_name": "Moving Average Convergence Divergence (MACD)",
    "category": "momentum",
    "description": "Shows the relationship between two moving averages of prices",
    "parameters": [
      {
        "name": "fast",
        "type": "integer",
        "default": 12,
        "min": 2,
        "max": 50,
        "description": "Fast period",
        "required": true
      },
      {
        "name": "slow",
        "type": "integer",
        "default": 26,
        "min": 2,
        "max": 100,
        "description": "Slow period",
        "required": true
      },
      {
        "name": "signal",
        "type": "integer",
        "default": 9,
        "min": 2,
        "max": 50,
        "description": "Signal line period",
        "required": true
      }
    ],
    "outputs": ["MACD", "MACDh", "MACDs"],
    "is_custom": false
  }
}
```

**Example Requests**:
```bash
# Get RSI definition
curl http://localhost:8081/indicators/definition/RSI

# Get MACD definition
curl http://localhost:8081/indicators/definition/MACD

# Get Bollinger Bands definition
curl http://localhost:8081/indicators/definition/BBANDS
```

---

## Available Indicators

### Momentum Indicators (11)
- **RSI** - Relative Strength Index
- **MACD** - Moving Average Convergence Divergence
- **STOCH** - Stochastic Oscillator
- **STOCHRSI** - Stochastic RSI
- **CCI** - Commodity Channel Index
- **MOM** - Momentum
- **ROC** - Rate of Change
- **TSI** - True Strength Index
- **WILLR** - Williams %R
- **AO** - Awesome Oscillator
- **PPO** - Percentage Price Oscillator

### Trend Indicators (11)
- **SMA** - Simple Moving Average
- **EMA** - Exponential Moving Average
- **WMA** - Weighted Moving Average
- **HMA** - Hull Moving Average
- **DEMA** - Double Exponential Moving Average
- **TEMA** - Triple Exponential Moving Average
- **VWMA** - Volume Weighted Moving Average
- **ZLEMA** - Zero Lag Exponential Moving Average
- **KAMA** - Kaufman Adaptive Moving Average
- **MAMA** - MESA Adaptive Moving Average
- **T3** - T3 Moving Average

### Volatility Indicators (5)
- **ATR** - Average True Range
- **NATR** - Normalized Average True Range
- **BBANDS** - Bollinger Bands
- **KC** - Keltner Channels
- **DC** - Donchian Channels

### Volume Indicators (5)
- **OBV** - On Balance Volume
- **AD** - Accumulation/Distribution
- **ADX** - Average Directional Index
- **VWAP** - Volume Weighted Average Price
- **MFI** - Money Flow Index

### Other Indicators (4)
- **PSAR** - Parabolic SAR
- **SUPERTREND** - SuperTrend
- **AROON** - Aroon Indicator
- **FISHER** - Fisher Transform

**Total: 41 built-in indicators**

---

## Frontend Integration Guide

### 1. **Fetch Indicator List on Page Load**

```javascript
// Fetch all indicators
const response = await fetch('http://localhost:8081/indicators/list');
const data = await response.json();

console.log(`Total indicators: ${data.total}`);
console.log(`Categories: ${data.categories.join(', ')}`);

// Store in state
const [indicators, setIndicators] = useState(data.indicators);
const [categories] = useState(data.categories);
```

### 2. **Build Category Tabs**

```javascript
// Group indicators by category
const indicatorsByCategory = {};
data.categories.forEach(cat => {
  indicatorsByCategory[cat] = data.indicators.filter(
    ind => ind.category === cat
  );
});

// Render tabs
<Tabs>
  {categories.map(category => (
    <Tab key={category} label={category}>
      <IndicatorList indicators={indicatorsByCategory[category]} />
    </Tab>
  ))}
</Tabs>
```

### 3. **Render Indicator Buttons**

```javascript
function IndicatorList({ indicators }) {
  return (
    <div className="indicator-grid">
      {indicators.map(indicator => (
        <IndicatorButton
          key={indicator.name}
          indicator={indicator}
          onClick={() => handleIndicatorSelect(indicator)}
        />
      ))}
    </div>
  );
}
```

### 4. **Dynamic Parameter Form**

```javascript
function IndicatorParameterForm({ indicator }) {
  const [params, setParams] = useState(
    indicator.parameters.reduce((acc, param) => ({
      ...acc,
      [param.name]: param.default
    }), {})
  );

  return (
    <form>
      <h3>{indicator.display_name}</h3>
      <p>{indicator.description}</p>

      {indicator.parameters.map(param => (
        <div key={param.name} className="param-field">
          <label>
            {param.description}
            {param.required && <span className="required">*</span>}
          </label>

          {param.type === 'integer' && (
            <input
              type="number"
              value={params[param.name]}
              min={param.min}
              max={param.max}
              step={1}
              onChange={e => setParams({
                ...params,
                [param.name]: parseInt(e.target.value)
              })}
            />
          )}

          {param.type === 'float' && (
            <input
              type="number"
              value={params[param.name]}
              min={param.min}
              max={param.max}
              step={0.01}
              onChange={e => setParams({
                ...params,
                [param.name]: parseFloat(e.target.value)
              })}
            />
          )}

          <small>
            Default: {param.default} | Range: [{param.min}, {param.max}]
          </small>
        </div>
      ))}

      <button onClick={() => handleSubscribe(indicator, params)}>
        Subscribe
      </button>
    </form>
  );
}
```

### 5. **Subscribe to Indicator**

```javascript
async function handleSubscribe(indicator, params) {
  // Build indicator ID from name and parameters
  const indicatorId = buildIndicatorId(indicator.name, params);

  // Subscribe via API
  const response = await fetch('http://localhost:8081/indicators/subscribe', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${accessToken}`
    },
    body: JSON.stringify({
      symbol: 'NIFTY50',
      timeframe: '5min',
      indicators: [{
        name: indicator.name,
        params: params
      }]
    })
  });

  console.log('Subscribed to', indicatorId);
}

function buildIndicatorId(name, params) {
  // RSI with length=14, scalar=100 → "RSI_14_100"
  // MACD with fast=12, slow=26, signal=9 → "MACD_12_26_9"
  const paramValues = Object.values(params);
  return [name, ...paramValues].join('_');
}
```

### 6. **Search/Autocomplete**

```javascript
function IndicatorSearch() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);

  const handleSearch = async (searchQuery) => {
    const response = await fetch(
      `http://localhost:8081/indicators/list?search=${encodeURIComponent(searchQuery)}`
    );
    const data = await response.json();
    setResults(data.indicators);
  };

  return (
    <div>
      <input
        type="text"
        placeholder="Search indicators..."
        value={query}
        onChange={e => {
          setQuery(e.target.value);
          if (e.target.value.length > 2) {
            handleSearch(e.target.value);
          }
        }}
      />

      {results.length > 0 && (
        <div className="search-results">
          {results.map(indicator => (
            <div key={indicator.name} onClick={() => handleSelect(indicator)}>
              <strong>{indicator.display_name}</strong>
              <p>{indicator.description}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

---

## Data Structure Reference

### Indicator Definition

```typescript
interface IndicatorDefinition {
  name: string;              // API identifier (e.g., "RSI")
  display_name: string;      // User-friendly name (e.g., "Relative Strength Index (RSI)")
  category: "momentum" | "trend" | "volatility" | "volume" | "other" | "custom";
  description: string;       // What the indicator does
  parameters: ParameterDefinition[];  // Parameter specs
  outputs: string[];         // Output field names (e.g., ["RSI"] or ["MACD", "MACDh", "MACDs"])
  is_custom: boolean;        // true for user-defined indicators
  author?: string;           // For custom indicators
  created_at?: string;       // ISO timestamp for custom indicators
}
```

### Parameter Definition

```typescript
interface ParameterDefinition {
  name: string;              // Parameter name (e.g., "length")
  type: "integer" | "float" | "boolean" | "string";
  default: any;              // Default value
  min?: number;              // Minimum value (for numeric types)
  max?: number;              // Maximum value (for numeric types)
  description: string;       // User-friendly description
  required: boolean;         // Whether this parameter must be provided
}
```

---

## Future: Custom User-Defined Indicators

The registry is designed to support custom indicators written by users. The workflow will be:

### 1. **User Writes Custom Indicator** (Python)

```python
# File: my_custom_indicator.py

import pandas as pd
import numpy as np

def my_custom_rsi(ohlcv: pd.DataFrame, length: int = 10, multiplier: float = 1.5) -> pd.Series:
    """
    Custom RSI variant with multiplier.

    Parameters:
    - length (int): Period length (default: 10, range: 2-50)
    - multiplier (float): Output multiplier (default: 1.5, range: 1.0-3.0)
    """
    # Calculate RSI
    delta = ohlcv['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=length).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=length).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    # Apply multiplier
    return rsi * multiplier
```

### 2. **User Registers Indicator**

```bash
POST /indicators/custom/register
{
  "name": "MY_CUSTOM_RSI",
  "display_name": "My Custom RSI",
  "category": "custom",
  "description": "RSI variant with multiplier",
  "code": "...python code...",
  "parameters": [
    {"name": "length", "type": "integer", "default": 10, "min": 2, "max": 50},
    {"name": "multiplier", "type": "float", "default": 1.5, "min": 1.0, "max": 3.0}
  ],
  "outputs": ["MY_CUSTOM_RSI"]
}
```

### 3. **Backend Validates and Stores**

- Syntax validation
- Security checks (no dangerous operations)
- Sandbox execution test
- Store in database with `user_id`, `created_at`

### 4. **Indicator Appears in Registry**

```bash
GET /indicators/list?category=custom
# Returns user's custom indicators with is_custom=true
```

### 5. **Subscribe Like Any Other Indicator**

```bash
POST /indicators/subscribe
{
  "symbol": "NIFTY50",
  "timeframe": "5min",
  "indicators": [
    {"name": "MY_CUSTOM_RSI", "params": {"length": 10, "multiplier": 1.5}}
  ]
}
```

**Same subscription architecture applies**: Reference counting, TTL, shared computation across users.

---

## Benefits

### For Frontend Developers

1. **No Hardcoding**: Indicator list is dynamic - add new indicators without frontend changes
2. **Type-Safe Forms**: Parameter metadata includes types, ranges, defaults for validation
3. **Self-Documenting**: Descriptions and help text come from API
4. **Search/Filter**: Built-in category filtering and search
5. **Extensible**: Custom indicators work exactly like built-in ones

### For Backend Developers

1. **Single Source of Truth**: Indicator definitions in one place
2. **Consistent API**: Same subscription/caching architecture for all indicators
3. **Easy to Extend**: Add new indicators by registering in `IndicatorRegistry`
4. **Validation Ready**: Parameter specs enable automatic validation

### For Users

1. **Discoverability**: Browse all available indicators with descriptions
2. **Guided Configuration**: Clear parameter names, ranges, and defaults
3. **Custom Indicators**: Write and share custom indicators in Python
4. **Consistent UX**: All indicators behave the same way

---

## Testing

Run the test script to verify the endpoint:

```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/python-sdk
chmod +x test_indicator_registry.py
python3 test_indicator_registry.py
```

**Expected Output**:
```
Test 1: List all indicators
────────────────────────────────────────────────────────────────────────────────
Status: 200
Total indicators: 41
Categories: momentum, trend, volatility, volume, other

First 5 indicators:
  RSI             - Relative Strength Index (RSI)
                    Category: momentum, Params: length(14), scalar(100)
                    Outputs: RSI
...
```

---

## Summary

The Indicator Registry API provides a **discovery endpoint** that:

✅ Lists all 41 built-in pandas_ta indicators
✅ Provides complete metadata (name, description, parameters, outputs)
✅ Supports filtering by category and search
✅ Enables dynamic frontend UI generation
✅ Ready for custom user-defined indicators
✅ Works with the subscription architecture (reference counting, caching)

This eliminates hardcoding in the frontend and makes the system fully extensible for custom indicators in the future.
