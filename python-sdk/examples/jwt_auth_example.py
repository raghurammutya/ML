"""
Example demonstrating JWT authentication with the StocksBlitz SDK.

This is the recommended method for user-facing applications.
"""

import sys
sys.path.insert(0, '/home/stocksadmin/Quantagro/tradingview-viz/python-sdk')

from stocksblitz import TradingClient, AuthenticationError


def main():
    print("=" * 60)
    print("StocksBlitz SDK - JWT Authentication Example")
    print("=" * 60)
    print()

    # Method 1: Using from_credentials() - Recommended
    print("Method 1: from_credentials() - One-step authentication")
    print("-" * 60)

    try:
        client = TradingClient.from_credentials(
            api_url="http://localhost:8081",
            user_service_url="http://localhost:8001",
            username="sdk_test@example.com",  # Test user email
            password="SecurePassword123!",  # Test user password
            persist_session=True  # Get refresh token for long sessions
        )

        print(f"✓ Successfully authenticated!")
        print(f"  Client: {client}")
        print()

        # Now you can use the client - it will auto-refresh tokens
        print("Testing API call (should work with JWT):")
        try:
            # Example: Get health status
            result = client._api.get("/health")
            print(f"✓ API call successful: {result.get('status', 'N/A')}")
        except Exception as e:
            print(f"✗ API call failed: {e}")

        print()

    except AuthenticationError as e:
        print(f"✗ Authentication failed: {e}")
        return
    except Exception as e:
        print(f"✗ Error: {e}")
        return

    # Method 2: Two-step authentication
    print()
    print("Method 2: Two-step authentication")
    print("-" * 60)

    try:
        # Step 1: Create client with user_service_url
        client2 = TradingClient(
            api_url="http://localhost:8081",
            user_service_url="http://localhost:8001"
        )

        print(f"✓ Client created: {client2}")

        # Step 2: Login manually
        login_result = client2.login("sdk_test@example.com", "SecurePassword123!")
        print(f"✓ Login successful!")
        print(f"  User: {login_result.get('user', {}).get('email', 'N/A')}")
        print(f"  Access token expires in: {login_result.get('expires_in', 0)} seconds")
        print()

        # Test API call
        print("Testing API call:")
        result = client2._api.get("/health")
        print(f"✓ API call successful: {result.get('status', 'N/A')}")

        print()

        # Logout
        print("Logging out...")
        client2.logout()
        print("✓ Logged out successfully")

    except AuthenticationError as e:
        print(f"✗ Authentication failed: {e}")
    except Exception as e:
        print(f"✗ Error: {e}")

    print()
    print("=" * 60)
    print("JWT Authentication Examples Complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
