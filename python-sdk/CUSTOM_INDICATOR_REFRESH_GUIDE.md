# Custom Indicator Refresh Guide

## Problem

When you add a custom Python indicator or modify an existing one on the backend, the SDK's indicator registry cache becomes stale. You need to force a refresh to see the new or updated indicators.

## Solution: 5 Methods to Force Refresh

The SDK provides **5 different methods** to force refresh the indicator registry. Choose the one that best fits your workflow.

---

## Method 1: Programmatic Force Refresh (Recommended)

Use the `force_refresh` parameter when fetching indicators.

**Use Case**: Scripts that need fresh data on each run, or after making backend changes.

```python
from stocksblitz import TradingClient

client = TradingClient.from_credentials(
    api_url="http://localhost:8081",
    user_service_url="http://localhost:8001",
    username="your@email.com",
    password="your_password"
)

# Force refresh - bypasses all caches and fetches from API
client.indicators.fetch_indicators(force_refresh=True)

# Now you'll see your new custom indicator
indicators = client.indicators.list_indicators(category="custom")
for ind in indicators:
    print(f"  {ind['name']}: {ind['display_name']}")
```

**Pros**:
- Fine-grained control
- Works in all environments
- No file system changes needed

**Cons**:
- Requires code modification

---

## Method 2: Clear Cache Method

Call `clear_cache()` to delete both in-memory and disk cache.

**Use Case**: Interactive scripts, Jupyter notebooks, or when you want explicit control.

```python
from stocksblitz import TradingClient

client = TradingClient.from_credentials(
    api_url="http://localhost:8081",
    user_service_url="http://localhost:8001",
    username="your@email.com",
    password="your_password"
)

# Clear all caches (in-memory + disk)
client.indicators.clear_cache()

# Next call will fetch fresh data from API
indicators = client.indicators.list_indicators()
```

**Pros**:
- Explicit and clear
- Works in interactive environments
- Immediate effect

**Cons**:
- Requires code modification

---

## Method 3: Delete Cache File

Delete the disk cache file manually.

**Use Case**: Quick one-time refresh without modifying code. Testing and debugging.

```bash
# Delete the cache file
rm ~/.stocksblitz/indicator_registry.json

# Or on Windows:
# del %USERPROFILE%\.stocksblitz\indicator_registry.json
```

Now run your Python script normally:

```python
from stocksblitz import TradingClient

# Cache file is gone, so SDK will fetch from API automatically
client = TradingClient.from_credentials(...)
indicators = client.indicators.list_indicators()
```

**Pros**:
- No code changes needed
- Quick and simple
- Works for any script

**Cons**:
- Requires manual file deletion each time
- Platform-specific command

---

## Method 4: Environment Variable

Set `STOCKSBLITZ_FORCE_REFRESH=1` to force refresh for all scripts.

**Use Case**: Development environment, testing new indicators, CI/CD pipelines.

### Unix/Linux/Mac:

```bash
# Set for single command
STOCKSBLITZ_FORCE_REFRESH=1 python your_script.py

# Or export for entire session
export STOCKSBLITZ_FORCE_REFRESH=1
python your_script.py
python another_script.py  # Also refreshes

# Unset when done
unset STOCKSBLITZ_FORCE_REFRESH
```

### Windows (CMD):

```cmd
set STOCKSBLITZ_FORCE_REFRESH=1
python your_script.py

rem Unset when done
set STOCKSBLITZ_FORCE_REFRESH=
```

### Windows (PowerShell):

```powershell
$env:STOCKSBLITZ_FORCE_REFRESH="1"
python your_script.py

# Unset when done
Remove-Item Env:\STOCKSBLITZ_FORCE_REFRESH
```

**Pros**:
- No code changes needed
- Works for all scripts in the session
- Great for development/testing

**Cons**:
- Requires setting environment variable
- Easy to forget to unset

---

## Method 5: Disable Disk Cache

Disable persistent disk caching entirely (always fetch from API).

**Use Case**: Testing, debugging, or when indicators change very frequently.

```python
from stocksblitz import TradingClient

# Disable disk cache - always fetches from API
client = TradingClient.from_credentials(
    api_url="http://localhost:8081",
    user_service_url="http://localhost:8001",
    username="your@email.com",
    password="your_password",
    enable_disk_cache=False  # Disable persistent cache
)

# First call fetches from API (~85ms)
indicators = client.indicators.list_indicators()

# Second call ALSO fetches from API (~85ms)
# (but in-memory cache still works within same session)
indicators = client.indicators.list_indicators()
```

**Pros**:
- Simple configuration
- Always fresh data
- No cache management needed

**Cons**:
- Slower performance (API call on each new session)
- Wastes bandwidth if indicators don't change often

---

## Complete Workflow: Adding a Custom Indicator

### Step 1: Add Custom Indicator on Backend

```python
# backend/app/services/indicator_registry.py

# Add your custom indicator definition
from app.services.indicator_registry import get_indicator_registry, IndicatorDefinition, IndicatorParameter, IndicatorCategory, ParameterType

registry = get_indicator_registry()

# Register your custom indicator
registry.register(IndicatorDefinition(
    name="MY_CUSTOM_RSI",
    display_name="My Custom RSI with Multiplier",
    category=IndicatorCategory.CUSTOM,
    description="Custom RSI variant with multiplier parameter",
    parameters=[
        IndicatorParameter("length", ParameterType.INTEGER, 10, 2, 50, "Period length"),
        IndicatorParameter("multiplier", ParameterType.FLOAT, 1.5, 1.0, 3.0, "Output multiplier")
    ],
    outputs=["MY_CUSTOM_RSI"],
    is_custom=True,
    author="your@email.com",
    created_at=datetime.now().isoformat()
))
```

### Step 2: Restart Backend Service

```bash
# Restart backend to load new indicator
docker-compose restart backend

# Or if running manually:
# Ctrl+C to stop
# python -m uvicorn app.main:app --reload
```

### Step 3: Force Refresh in SDK

**Option A**: Programmatic (best for production):

```python
from stocksblitz import TradingClient

client = TradingClient.from_credentials(...)

# Force refresh to see new indicator
client.indicators.fetch_indicators(force_refresh=True)

# Verify it's there
custom_indicators = client.indicators.list_indicators(category="custom")
for ind in custom_indicators:
    if ind['name'] == "MY_CUSTOM_RSI":
        print(f"✓ Found: {ind['display_name']}")
        print(f"  Parameters: {[p['name'] for p in ind['parameters']]}")
```

**Option B**: Delete cache file (best for quick testing):

```bash
# Delete cache
rm ~/.stocksblitz/indicator_registry.json

# Run script
python test_my_custom_indicator.py
```

**Option C**: Environment variable (best for development):

```bash
# Set env var for all scripts
export STOCKSBLITZ_FORCE_REFRESH=1

# Run any script
python test_my_custom_indicator.py
python another_test.py

# Unset when done
unset STOCKSBLITZ_FORCE_REFRESH
```

### Step 4: Use Your Custom Indicator

```python
from stocksblitz import TradingClient

client = TradingClient.from_credentials(...)

# Validate parameters before subscribing
try:
    client.indicators.validate_indicator(
        "MY_CUSTOM_RSI",
        {"length": 10, "multiplier": 1.5}
    )
    print("✓ Parameters valid")
except Exception as e:
    print(f"✗ Validation error: {e}")

# Subscribe to your custom indicator
# (subscription endpoint not yet implemented, but validation works now)
```

---

## Cache Behavior Summary

### Without Force Refresh:
```
Session 1:
  ├─ First call  → Loads from disk cache (~2ms) OR API if cache missing (~85ms)
  ├─ Second call → Loads from in-memory cache (<0.05ms)
  └─ Third call  → Loads from in-memory cache (<0.05ms)

Session 2 (new Python process):
  ├─ First call  → Loads from disk cache (~2ms)
  ├─ Second call → Loads from in-memory cache (<0.05ms)
  └─ Third call  → Loads from in-memory cache (<0.05ms)

After 24 hours (cache TTL expires):
  └─ Next call → Fetches from API (~85ms), updates disk cache
```

### With Force Refresh:
```
Session 1:
  ├─ First call (force_refresh=True)  → Fetches from API (~85ms)
  ├─ Second call (no force)           → Loads from in-memory cache (<0.05ms)
  └─ Third call (force_refresh=True)  → Fetches from API (~85ms)
```

---

## Performance Impact

| Method | Performance Impact | When to Use |
|--------|-------------------|-------------|
| No refresh (default) | Best (~2ms first call, <0.05ms subsequent) | Production, stable indicators |
| Method 1 (programmatic) | Medium (~85ms when forced) | After known backend changes |
| Method 2 (clear_cache) | Medium (~85ms next call) | Interactive development |
| Method 3 (delete file) | Medium (~85ms next run) | Quick testing |
| Method 4 (env var) | Medium (~85ms per session) | Development environment |
| Method 5 (disable cache) | Worst (~85ms per session) | Testing only |

**Recommendation**: Use disk caching (default) in production, and force refresh only when you've explicitly added/modified indicators.

---

## FAQ

### Q: How often does the cache auto-refresh?

A: Every 24 hours by default (configurable via `cache_ttl` parameter).

```python
# Custom TTL: refresh every 6 hours
client = TradingClient.from_credentials(
    ...,
    cache_ttl=21600  # 6 hours in seconds
)
```

### Q: Will I miss new indicators if I don't force refresh?

A: No, the cache auto-refreshes after 24 hours. But if you add a custom indicator and want to use it immediately, use one of the 5 force refresh methods.

### Q: Which method is best for production?

A: **Method 1 (programmatic)** is best for production:
- Fine-grained control
- Explicit in code (self-documenting)
- Works in all environments

### Q: Which method is best for development?

A: **Method 4 (environment variable)** is best for development:
- No code changes needed
- Works for all scripts
- Easy to enable/disable

### Q: Can I check cache status?

A: Yes:

```python
from pathlib import Path
import json
import time

cache_file = Path.home() / ".stocksblitz" / "indicator_registry.json"

if cache_file.exists():
    with open(cache_file) as f:
        cache_data = json.load(f)

    cached_at = cache_data.get("cached_at", 0)
    age_hours = (time.time() - cached_at) / 3600

    print(f"Cache age: {age_hours:.1f} hours")
    print(f"Cache TTL: 24 hours")
    print(f"Indicators cached: {len(cache_data.get('indicators', {}))}")
    print(f"Cache version: {cache_data.get('version')}")

    if age_hours < 24:
        print("✓ Cache is fresh")
    else:
        print("⚠ Cache is stale (will auto-refresh on next call)")
else:
    print("No cache file found (will fetch from API on next call)")
```

---

## Summary

When you add or modify a custom indicator:

1. **Development**: Use `export STOCKSBLITZ_FORCE_REFRESH=1` (Method 4)
2. **Production**: Use `client.indicators.fetch_indicators(force_refresh=True)` (Method 1)
3. **Quick Testing**: Use `rm ~/.stocksblitz/indicator_registry.json` (Method 3)

The SDK provides flexible caching with multiple force refresh options to suit any workflow.
