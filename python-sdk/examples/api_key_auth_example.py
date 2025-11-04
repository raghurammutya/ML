"""
Example demonstrating API Key authentication with the StocksBlitz SDK.

This is the recommended method for:
- Server-to-server communication
- Automated trading bots
- Background scripts
- CI/CD pipelines
"""

import sys
sys.path.insert(0, '/home/stocksadmin/Quantagro/tradingview-viz/python-sdk')

from stocksblitz import TradingClient, AuthenticationError


def main():
    print("=" * 60)
    print("StocksBlitz SDK - API Key Authentication Example")
    print("=" * 60)
    print()

    # API Key format: sb_{prefix}_{secret}
    # Example: sb_30d4d5ea_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6
    api_key = "sb_test1234_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0"  # Replace with real key

    print("Initializing client with API key...")
    print(f"API Key: {api_key[:20]}...")  # Show first 20 chars only
    print()

    try:
        # Initialize with API key
        client = TradingClient(
            api_url="http://localhost:8081",
            api_key=api_key
        )

        print(f"✓ Client initialized: {client}")
        print()

        # Test API call
        print("Testing API call with API key:")
        try:
            result = client._api.get("/health")
            print(f"✓ API call successful!")
            print(f"  Status: {result.get('status', 'N/A')}")
            print(f"  Database: {result.get('database', 'N/A')}")
            print(f"  Redis: {result.get('redis', 'N/A')}")
        except AuthenticationError as e:
            print(f"✗ Authentication failed: {e}")
            print()
            print("Note: To test API key auth, you need to:")
            print("  1. Create an API key in the backend database")
            print("  2. Or use the backend API: POST /api/keys/create")
        except Exception as e:
            print(f"✗ API call failed: {e}")

        print()

    except ValueError as e:
        print(f"✗ Configuration error: {e}")
    except Exception as e:
        print(f"✗ Error: {e}")

    print()
    print("=" * 60)
    print("API Key Authentication Example Complete")
    print("=" * 60)
    print()
    print("Important Notes:")
    print("- API keys are long-lived and must be explicitly revoked")
    print("- Store API keys securely (environment variables, secrets manager)")
    print("- Never commit API keys to version control")
    print("- Use different keys for dev/staging/production")
    print("- Monitor API key usage via backend logs")


if __name__ == "__main__":
    main()
