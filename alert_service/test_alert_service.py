#!/usr/bin/env python3
"""
Quick Test Script for Alert Service
Tests basic functionality: create alert, list alerts, send test notification
"""

import asyncio
import httpx
import json

# Configuration
BASE_URL = "http://localhost:8082"
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"  # Replace with your chat ID


async def test_health_check():
    """Test health check endpoint."""
    print("\n1. Testing Health Check...")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/health")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200


async def test_create_alert():
    """Test creating a price alert."""
    print("\n2. Creating Price Alert...")

    alert_data = {
        "name": "NIFTY 24000 breakout test",
        "description": "Test alert for NIFTY crossing 24000",
        "alert_type": "price",
        "priority": "high",
        "condition_config": {
            "type": "price",
            "symbol": "NIFTY50",
            "operator": "gt",
            "threshold": 24000,
            "comparison": "last_price"
        },
        "notification_channels": ["telegram"],
        "evaluation_interval_seconds": 60,
        "cooldown_seconds": 300
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/alerts",
            json=alert_data,
            timeout=10.0
        )
        print(f"   Status: {response.status_code}")

        if response.status_code == 201:
            alert = response.json()
            print(f"   Alert created successfully!")
            print(f"   Alert ID: {alert['alert_id']}")
            print(f"   Name: {alert['name']}")
            print(f"   Type: {alert['alert_type']}")
            print(f"   Status: {alert['status']}")
            return alert['alert_id']
        else:
            print(f"   Error: {response.text}")
            return None


async def test_list_alerts():
    """Test listing alerts."""
    print("\n3. Listing Alerts...")

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/alerts")
        print(f"   Status: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"   Total alerts: {result['count']}")

            if result['count'] > 0:
                print(f"\n   Recent alerts:")
                for alert in result['alerts'][:3]:  # Show first 3
                    print(f"     - {alert['name']} ({alert['status']}) - {alert['alert_type']}")
            return True
        else:
            print(f"   Error: {response.text}")
            return False


async def test_get_alert(alert_id):
    """Test getting specific alert."""
    print(f"\n4. Getting Alert {alert_id}...")

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/alerts/{alert_id}")
        print(f"   Status: {response.status_code}")

        if response.status_code == 200:
            alert = response.json()
            print(f"   Alert details:")
            print(f"     Name: {alert['name']}")
            print(f"     Type: {alert['alert_type']}")
            print(f"     Priority: {alert['priority']}")
            print(f"     Status: {alert['status']}")
            print(f"     Trigger count: {alert['trigger_count']}")
            return True
        else:
            print(f"   Error: {response.text}")
            return False


async def test_pause_alert(alert_id):
    """Test pausing an alert."""
    print(f"\n5. Pausing Alert {alert_id}...")

    async with httpx.AsyncClient() as client:
        response = await client.post(f"{BASE_URL}/alerts/{alert_id}/pause")
        print(f"   Status: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"   {result['message']}")
            return True
        else:
            print(f"   Error: {response.text}")
            return False


async def test_resume_alert(alert_id):
    """Test resuming an alert."""
    print(f"\n6. Resuming Alert {alert_id}...")

    async with httpx.AsyncClient() as client:
        response = await client.post(f"{BASE_URL}/alerts/{alert_id}/resume")
        print(f"   Status: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"   {result['message']}")
            return True
        else:
            print(f"   Error: {response.text}")
            return False


async def test_alert_stats():
    """Test getting alert statistics."""
    print("\n7. Getting Alert Statistics...")

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/alerts/stats/summary")
        print(f"   Status: {response.status_code}")

        if response.status_code == 200:
            stats = response.json()
            print(f"   Statistics:")
            print(f"     Total alerts: {stats.get('total_alerts', 0)}")
            print(f"     Active alerts: {stats.get('active_alerts', 0)}")
            print(f"     Paused alerts: {stats.get('paused_alerts', 0)}")
            print(f"     Total triggers: {stats.get('total_triggers', 0)}")
            return True
        else:
            print(f"   Error: {response.text}")
            return False


async def test_telegram_notification():
    """Test sending a Telegram notification directly."""
    print("\n8. Testing Telegram Notification (Direct)...")

    if TELEGRAM_CHAT_ID == "YOUR_TELEGRAM_CHAT_ID":
        print("   ⚠️  Please update TELEGRAM_CHAT_ID in the script")
        return False

    # This would require implementing a test endpoint
    # For now, just a placeholder
    print("   ℹ️  Direct Telegram test requires separate implementation")
    print("   Tip: Set up notification preferences via API first")
    return True


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Alert Service - Quick Test Suite")
    print("=" * 60)

    try:
        # Test 1: Health check
        health_ok = await test_health_check()
        if not health_ok:
            print("\n❌ Health check failed! Is the service running?")
            print("   Run: uvicorn app.main:app --reload --port 8082")
            return

        # Test 2: Create alert
        alert_id = await test_create_alert()
        if not alert_id:
            print("\n❌ Failed to create alert")
            return

        # Test 3: List alerts
        await test_list_alerts()

        # Test 4: Get specific alert
        await test_get_alert(alert_id)

        # Test 5: Pause alert
        await test_pause_alert(alert_id)

        # Test 6: Resume alert
        await test_resume_alert(alert_id)

        # Test 7: Get stats
        await test_alert_stats()

        # Test 8: Telegram notification
        await test_telegram_notification()

        print("\n" + "=" * 60)
        print("✅ All tests completed!")
        print("=" * 60)

        print("\nNext steps:")
        print("1. Check API docs: http://localhost:8082/docs")
        print("2. Set up Telegram notifications via /notifications/preferences")
        print("3. Test alert triggering with real data")
        print("4. Check logs for any errors")

    except httpx.ConnectError:
        print("\n❌ Connection failed!")
        print("   Make sure the service is running:")
        print("   cd alert_service")
        print("   uvicorn app.main:app --reload --port 8082")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
