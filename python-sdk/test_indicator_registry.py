#!/usr/bin/env python3
"""
Test Indicator Registry API
Tests the /indicators/list endpoint for frontend discovery
"""

import requests
import json

# Config
API_URL = "http://localhost:8081"

def print_section(title):
    print(f"\n{'='*80}")
    print(f"{title}".center(80))
    print(f"{'='*80}\n")

def print_indicator_summary(indicator):
    """Print compact indicator summary"""
    params_str = ", ".join([
        f"{p['name']}({p['default']})"
        for p in indicator['parameters']
    ]) if indicator['parameters'] else "No parameters"

    print(f"  {indicator['name']:<15} - {indicator['display_name']}")
    print(f"  {'':15}   Category: {indicator['category']}, Params: {params_str}")
    print(f"  {'':15}   Outputs: {', '.join(indicator['outputs'])}")

def main():
    print_section("Indicator Registry API Test")

    # Test 1: List all indicators
    print("Test 1: List all indicators")
    print("─" * 80)
    try:
        response = requests.get(f"{API_URL}/indicators/list")
        data = response.json()

        print(f"Status: {response.status_code}")
        print(f"Total indicators: {data['total']}")
        print(f"Categories: {', '.join(data['categories'])}\n")

        # Show first 5 indicators
        print(f"First 5 indicators:")
        for ind in data['indicators'][:5]:
            print_indicator_summary(ind)
            print()

    except Exception as e:
        print(f"Error: {e}\n")

    # Test 2: Filter by category - Momentum
    print("\nTest 2: Filter by category (Momentum)")
    print("─" * 80)
    try:
        response = requests.get(f"{API_URL}/indicators/list?category=momentum")
        data = response.json()

        print(f"Status: {response.status_code}")
        print(f"Momentum indicators: {data['total']}\n")

        for ind in data['indicators']:
            print(f"  • {ind['name']:<10} - {ind['display_name']}")

    except Exception as e:
        print(f"Error: {e}")

    # Test 3: Filter by category - Trend
    print("\n\nTest 3: Filter by category (Trend)")
    print("─" * 80)
    try:
        response = requests.get(f"{API_URL}/indicators/list?category=trend")
        data = response.json()

        print(f"Status: {response.status_code}")
        print(f"Trend indicators: {data['total']}\n")

        for ind in data['indicators']:
            print(f"  • {ind['name']:<10} - {ind['display_name']}")

    except Exception as e:
        print(f"Error: {e}")

    # Test 4: Search indicators
    print("\n\nTest 4: Search for 'moving average'")
    print("─" * 80)
    try:
        response = requests.get(f"{API_URL}/indicators/list?search=moving+average")
        data = response.json()

        print(f"Status: {response.status_code}")
        print(f"Found: {data['total']} indicators\n")

        for ind in data['indicators']:
            print(f"  • {ind['name']:<10} - {ind['display_name']}")

    except Exception as e:
        print(f"Error: {e}")

    # Test 5: Get specific indicator definition
    print("\n\nTest 5: Get RSI definition")
    print("─" * 80)
    try:
        response = requests.get(f"{API_URL}/indicators/definition/RSI")
        data = response.json()

        print(f"Status: {response.status_code}")
        ind = data['indicator']

        print(f"\nName: {ind['name']}")
        print(f"Display Name: {ind['display_name']}")
        print(f"Category: {ind['category']}")
        print(f"Description: {ind['description']}")
        print(f"\nParameters:")
        for param in ind['parameters']:
            required = "✓" if param['required'] else " "
            print(f"  [{required}] {param['name']:<12} ({param['type']:<8}): {param['description']}")
            print(f"      {'':12}  Default: {param['default']}, Range: [{param['min']}, {param['max']}]")

        print(f"\nOutputs: {', '.join(ind['outputs'])}")

    except Exception as e:
        print(f"Error: {e}")

    # Test 6: Get MACD definition
    print("\n\nTest 6: Get MACD definition")
    print("─" * 80)
    try:
        response = requests.get(f"{API_URL}/indicators/definition/MACD")
        data = response.json()

        print(f"Status: {response.status_code}")
        ind = data['indicator']

        print(f"\nName: {ind['name']}")
        print(f"Display Name: {ind['display_name']}")
        print(f"Description: {ind['description']}")
        print(f"\nParameters:")
        for param in ind['parameters']:
            print(f"  • {param['name']}: {param['default']} (range: {param['min']}-{param['max']})")

        print(f"\nOutputs: {', '.join(ind['outputs'])}")
        print(f"  ↳ MACD: Main line")
        print(f"  ↳ MACDh: Histogram")
        print(f"  ↳ MACDs: Signal line")

    except Exception as e:
        print(f"Error: {e}")

    # Test 7: Get Bollinger Bands definition
    print("\n\nTest 7: Get Bollinger Bands definition")
    print("─" * 80)
    try:
        response = requests.get(f"{API_URL}/indicators/definition/BBANDS")
        data = response.json()

        print(f"Status: {response.status_code}")
        ind = data['indicator']

        print(f"\nName: {ind['name']}")
        print(f"Display Name: {ind['display_name']}")
        print(f"Parameters:")
        for param in ind['parameters']:
            print(f"  • {param['name']}: {param['default']} ({param['type']})")

        print(f"\nOutputs: {', '.join(ind['outputs'])}")

    except Exception as e:
        print(f"Error: {e}")

    # Test 8: Get all categories
    print("\n\nTest 8: Get indicators grouped by category")
    print("─" * 80)
    try:
        categories = ["momentum", "trend", "volatility", "volume", "other"]

        for cat in categories:
            response = requests.get(f"{API_URL}/indicators/list?category={cat}")
            data = response.json()

            print(f"\n{cat.upper()} ({data['total']} indicators):")
            names = [ind['name'] for ind in data['indicators']]
            print(f"  {', '.join(names)}")

    except Exception as e:
        print(f"Error: {e}")

    print("\n" + "="*80)
    print("Tests Complete".center(80))
    print("="*80 + "\n")

    # Summary for frontend developers
    print_section("Frontend Integration Guide")
    print("""
The /indicators/list endpoint provides all necessary metadata for building
a dynamic indicator selection UI in the frontend:

1. **List all indicators**:
   GET /indicators/list
   → Use to build main indicator picker

2. **Filter by category**:
   GET /indicators/list?category=momentum
   → Use to show only specific types (tabs/dropdowns)

3. **Search indicators**:
   GET /indicators/list?search=moving
   → Use for search/autocomplete features

4. **Get specific definition**:
   GET /indicators/definition/RSI
   → Use to show detailed help/documentation

Each indicator includes:
- name: API identifier (e.g., "RSI")
- display_name: User-friendly name (e.g., "Relative Strength Index (RSI)")
- category: Group (momentum/trend/volatility/volume/other)
- description: What it does
- parameters: Array of parameter specs with:
  - name, type, default, min, max, description, required
  → Use to dynamically generate input fields
- outputs: Array of output field names
  → Use to understand what data will be returned
- is_custom: Boolean (true for user-defined indicators)

**Example frontend workflow**:
1. On page load: Fetch /indicators/list
2. Build category tabs (momentum, trend, etc.)
3. Render indicator buttons within each category
4. When user selects indicator:
   - Show parameter input fields (from parameters array)
   - Pre-fill with default values
   - Show min/max validation
5. When user submits:
   - Build indicator_id: "{name}_{param1}_{param2}"
   - Call /indicators/subscribe with the spec
""")

if __name__ == "__main__":
    main()
