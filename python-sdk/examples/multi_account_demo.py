"""
Multi-Account Support Demo

This example demonstrates the hybrid multi-account interface in the SDK.

Features:
1. Simple single-account usage (backward compatible)
2. Explicit multi-account access by account_id
3. Account discovery and listing
4. Primary account auto-selection
"""

from stocksblitz import TradingClient


def demo_simple_usage():
    """
    Simple usage - backward compatible.

    Uses primary account automatically.
    """
    print("\n=== Demo 1: Simple Usage (Backward Compatible) ===\n")

    # Create client with API key
    client = TradingClient(
        api_url="http://localhost:8010",
        api_key="sb_30d4d5ea_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6"
    )

    # Use Account() without arguments - automatically uses primary account
    account = client.Account()

    # Get positions
    positions = account.positions
    print(f"Positions in primary account: {len(positions)}")

    # Place order (on primary account)
    # order = account.buy("NIFTY50", quantity=50)
    # print(f"Order placed: {order}")


def demo_explicit_multi_account():
    """
    Explicit multi-account usage.

    Access specific accounts by account_id.
    """
    print("\n=== Demo 2: Explicit Multi-Account Access ===\n")

    # Login with JWT to get multi-account access
    client = TradingClient.from_credentials(
        api_url="http://localhost:8010",
        user_service_url="http://localhost:8011",
        username="trader@example.com",
        password="password123"
    )

    # List all accessible accounts
    print("Accessible accounts:")
    for account in client.Accounts.list():
        print(f"  - {account['account_id']}: {account['broker']} ({account['role']})")

    # Access specific account directly
    account_xj4540 = client.Accounts["XJ4540"]
    positions = account_xj4540.positions
    print(f"\nPositions in XJ4540: {len(positions)}")

    # Place order on specific account
    # order = account_xj4540.buy("NIFTY50", quantity=50)
    # print(f"Order on XJ4540: {order}")

    # Access another account
    if "AB1234" in client.Accounts:
        account_ab1234 = client.Accounts["AB1234"]
        print(f"Funds in AB1234: {account_ab1234.funds}")


def demo_account_discovery():
    """
    Account discovery and iteration.

    Discover available accounts at runtime.
    """
    print("\n=== Demo 3: Account Discovery ===\n")

    client = TradingClient.from_credentials(
        api_url="http://localhost:8010",
        user_service_url="http://localhost:8011",
        username="trader@example.com",
        password="password123"
    )

    # Check number of accounts
    print(f"Total accessible accounts: {len(client.Accounts)}")

    # Iterate over account IDs
    print("\nAccount IDs:")
    for account_id in client.Accounts:
        print(f"  - {account_id}")

    # Get primary account
    primary = client.Accounts.primary()
    print(f"\nPrimary account: {primary.account_id}")

    # Check if specific account exists
    if "XJ4540" in client.Accounts:
        print("Account XJ4540 is accessible")


def demo_hybrid_usage():
    """
    Hybrid usage - mix simple and explicit.

    Demonstrates flexibility of the hybrid interface.
    """
    print("\n=== Demo 4: Hybrid Usage ===\n")

    client = TradingClient.from_credentials(
        api_url="http://localhost:8010",
        user_service_url="http://localhost:8011",
        username="trader@example.com",
        password="password123"
    )

    # Simple usage for primary account
    primary_positions = client.Account().positions
    print(f"Primary account positions: {len(primary_positions)}")

    # Explicit access for other accounts
    for account_id in client.Accounts:
        account = client.Accounts[account_id]
        funds = account.funds
        print(f"{account_id}: Available cash = {funds.available_cash}")

    # Strategy using multiple accounts
    inst = client.Instrument("NIFTY50")
    if inst['5m'].rsi[14] > 70:
        # Sell on primary account
        # client.Account().sell(inst, quantity=50)
        print("Would sell on primary account")

        # Also sell on backup account if available
        if "BACKUP_ACCOUNT" in client.Accounts:
            # client.Accounts["BACKUP_ACCOUNT"].sell(inst, quantity=50)
            print("Would sell on backup account")


def demo_error_handling():
    """
    Error handling for multi-account scenarios.
    """
    print("\n=== Demo 5: Error Handling ===\n")

    client = TradingClient.from_credentials(
        api_url="http://localhost:8010",
        user_service_url="http://localhost:8011",
        username="trader@example.com",
        password="password123"
    )

    # Try to access non-existent account
    try:
        account = client.Accounts["INVALID_ACCOUNT"]
    except KeyError as e:
        print(f"Expected error: {e}")

    # Check account exists before accessing
    account_id = "XJ4540"
    if account_id in client.Accounts:
        account = client.Accounts[account_id]
        print(f"Successfully accessed {account_id}")
    else:
        print(f"Account {account_id} not accessible")


if __name__ == "__main__":
    print("=" * 60)
    print("Multi-Account Support Demo")
    print("=" * 60)

    # Run demos
    demo_simple_usage()
    demo_explicit_multi_account()
    demo_account_discovery()
    demo_hybrid_usage()
    demo_error_handling()

    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60)
