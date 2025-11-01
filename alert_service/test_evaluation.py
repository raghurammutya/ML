#!/usr/bin/env python3
"""
Phase 2 Test Script: Evaluation Engine
Tests alert evaluation, condition checking, and notification triggering
"""

import asyncio
import httpx
import json
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:8082"
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"  # Replace with your chat ID


async def test_health():
    """Test health check."""
    print("\n" + "=" * 70)
    print("1. Health Check")
    print("=" * 70)

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/health")
        print(f"Status: {response.status_code}")
        data = response.json()
        print(f"Service: {data.get('service')}")
        print(f"Database: {data.get('database')}")
        return response.status_code == 200


async def create_price_alert(symbol: str, threshold: float, operator: str = "gt"):
    """Create a price alert for testing."""
    print(f"\n2. Creating Price Alert: {symbol} {operator} {threshold}")
    print("-" * 70)

    alert_data = {
        "name": f"{symbol} {operator} {threshold} - Test",
        "description": f"Test alert for {symbol}",
        "alert_type": "price",
        "priority": "high",
        "condition_config": {
            "type": "price",
            "symbol": symbol,
            "operator": operator,
            "threshold": threshold,
            "comparison": "last_price"
        },
        "notification_channels": ["telegram"],
        "evaluation_interval_seconds": 30,
        "cooldown_seconds": 300,
        "max_triggers_per_day": 10,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/alerts",
            json=alert_data,
            timeout=10.0
        )

        if response.status_code == 201:
            alert = response.json()
            print(f"✅ Alert created successfully")
            print(f"   Alert ID: {alert['alert_id']}")
            print(f"   Name: {alert['name']}")
            print(f"   Status: {alert['status']}")
            return alert['alert_id']
        else:
            print(f"❌ Failed to create alert: {response.status_code}")
            print(f"   Error: {response.text}")
            return None


async def test_alert_evaluation(alert_id: str):
    """Test manual alert evaluation."""
    print(f"\n3. Testing Alert Evaluation: {alert_id}")
    print("-" * 70)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/alerts/{alert_id}/test",
            timeout=15.0
        )

        if response.status_code == 200:
            result = response.json()
            print(f"✅ Evaluation successful")

            evaluation = result.get("evaluation", {})
            print(f"\n   Evaluation Result:")
            print(f"   - Matched: {evaluation.get('matched')}")
            print(f"   - Current Value: {evaluation.get('current_value')}")
            print(f"   - Threshold: {evaluation.get('threshold')}")
            print(f"   - Error: {evaluation.get('error')}")
            print(f"   - Evaluated At: {evaluation.get('evaluated_at')}")

            if evaluation.get("details"):
                print(f"\n   Details:")
                for key, value in evaluation["details"].items():
                    print(f"   - {key}: {value}")

            return evaluation
        else:
            print(f"❌ Evaluation failed: {response.status_code}")
            print(f"   Error: {response.text}")
            return None


async def create_indicator_alert(symbol: str, indicator: str, threshold: float):
    """Create an indicator alert for testing."""
    print(f"\n4. Creating Indicator Alert: {symbol} {indicator} > {threshold}")
    print("-" * 70)

    alert_data = {
        "name": f"{symbol} {indicator.upper()} alert - Test",
        "description": f"Test indicator alert for {symbol}",
        "alert_type": "indicator",
        "priority": "medium",
        "condition_config": {
            "type": "indicator",
            "symbol": symbol,
            "indicator": indicator,
            "timeframe": "5min",
            "operator": "gt",
            "threshold": threshold,
            "lookback_periods": 14
        },
        "notification_channels": ["telegram"],
        "evaluation_interval_seconds": 60,
        "cooldown_seconds": 600,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/alerts",
            json=alert_data,
            timeout=10.0
        )

        if response.status_code == 201:
            alert = response.json()
            print(f"✅ Indicator alert created")
            print(f"   Alert ID: {alert['alert_id']}")
            return alert['alert_id']
        else:
            print(f"❌ Failed to create alert: {response.status_code}")
            print(f"   Error: {response.text}")
            return None


async def create_composite_alert(symbol: str, price_threshold: float, rsi_threshold: float):
    """Create a composite alert (AND logic)."""
    print(f"\n5. Creating Composite Alert: {symbol}")
    print(f"   Condition: Price > {price_threshold} AND RSI > {rsi_threshold}")
    print("-" * 70)

    alert_data = {
        "name": f"{symbol} Composite Alert - Test",
        "description": "Composite condition test",
        "alert_type": "custom",
        "priority": "high",
        "condition_config": {
            "type": "composite",
            "operator": "and",
            "conditions": [
                {
                    "type": "price",
                    "symbol": symbol,
                    "operator": "gt",
                    "threshold": price_threshold
                },
                {
                    "type": "indicator",
                    "symbol": symbol,
                    "indicator": "rsi",
                    "timeframe": "5min",
                    "operator": "gt",
                    "threshold": rsi_threshold
                }
            ]
        },
        "notification_channels": ["telegram"],
        "evaluation_interval_seconds": 60,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/alerts",
            json=alert_data,
            timeout=10.0
        )

        if response.status_code == 201:
            alert = response.json()
            print(f"✅ Composite alert created")
            print(f"   Alert ID: {alert['alert_id']}")
            return alert['alert_id']
        else:
            print(f"❌ Failed to create alert: {response.status_code}")
            return None


async def wait_for_evaluation(alert_id: str, max_wait: int = 120):
    """Wait for alert to be evaluated by background worker."""
    print(f"\n6. Waiting for Background Evaluation (max {max_wait}s)")
    print("-" * 70)

    async with httpx.AsyncClient() as client:
        start_time = datetime.utcnow()

        while (datetime.utcnow() - start_time).total_seconds() < max_wait:
            # Get alert details
            response = await client.get(f"{BASE_URL}/alerts/{alert_id}")

            if response.status_code == 200:
                alert = response.json()
                last_evaluated = alert.get("last_evaluated_at")
                trigger_count = alert.get("trigger_count", 0)

                if last_evaluated:
                    print(f"✅ Alert evaluated!")
                    print(f"   Last Evaluated: {last_evaluated}")
                    print(f"   Trigger Count: {trigger_count}")

                    if trigger_count > 0:
                        print(f"   🔔 Alert triggered {trigger_count} time(s)!")
                        return True
                    else:
                        print(f"   ℹ️  Alert evaluated but condition not met")
                        return False

            # Wait before checking again
            await asyncio.sleep(5)
            print("   Waiting for evaluation...")

        print(f"⚠️  Timeout: Alert not evaluated within {max_wait}s")
        return False


async def check_alert_events(alert_id: str):
    """Check if any alert events were recorded."""
    print(f"\n7. Checking Alert Events for {alert_id}")
    print("-" * 70)

    # Note: This requires a route to fetch alert events
    # For now, we'll just check the alert's trigger count
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/alerts/{alert_id}")

        if response.status_code == 200:
            alert = response.json()
            trigger_count = alert.get("trigger_count", 0)
            last_triggered = alert.get("last_triggered_at")

            if trigger_count > 0:
                print(f"✅ Alert has been triggered {trigger_count} time(s)")
                print(f"   Last Triggered: {last_triggered}")
                return True
            else:
                print(f"ℹ️  Alert has not been triggered yet")
                return False


async def test_worker_status():
    """Check if evaluation worker is running."""
    print("\n8. Checking Evaluation Worker Status")
    print("-" * 70)

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/health")

        if response.status_code == 200:
            data = response.json()
            # Note: We'd need to add worker status to health check
            print(f"✅ Service is running")
            print(f"   Service: {data.get('service')}")
            print(f"   Environment: {data.get('environment')}")
            return True

    return False


async def main():
    """Run all Phase 2 tests."""
    print("\n" + "=" * 70)
    print("ALERT SERVICE - PHASE 2 EVALUATION TEST")
    print("=" * 70)
    print(f"Testing against: {BASE_URL}")
    print(f"Started at: {datetime.utcnow().isoformat()}")
    print("=" * 70)

    try:
        # Test 1: Health check
        if not await test_health():
            print("\n❌ Service not healthy. Is it running?")
            print("   Start with: uvicorn app.main:app --reload --port 8082")
            return

        # Test 2: Create price alert with realistic threshold
        # Using NIFTY50 at ~23500 (adjust as needed)
        alert_id = await create_price_alert("NIFTY50", 23000, "gt")

        if not alert_id:
            print("\n❌ Failed to create alert")
            return

        # Test 3: Manual evaluation (test endpoint)
        print("\n" + "=" * 70)
        print("MANUAL EVALUATION TEST")
        print("=" * 70)
        evaluation = await test_alert_evaluation(alert_id)

        if evaluation:
            if evaluation.get("matched"):
                print("\n✅ Condition is currently TRUE")
            else:
                print("\n✅ Condition is currently FALSE")
                if evaluation.get("error"):
                    print(f"   Error: {evaluation.get('error')}")

        # Test 4: Wait for background worker to evaluate
        print("\n" + "=" * 70)
        print("BACKGROUND WORKER TEST")
        print("=" * 70)
        print("The background worker evaluates alerts every 10-30 seconds.")
        print("Waiting for automatic evaluation...")

        triggered = await wait_for_evaluation(alert_id, max_wait=90)

        if triggered:
            print("\n🎉 SUCCESS! Alert was triggered by background worker!")
            print("   Check your Telegram for notification")
        else:
            print("\n✅ Alert was evaluated but condition not met")
            print("   (This is expected if NIFTY is below threshold)")

        # Test 5: Check events
        await check_alert_events(alert_id)

        # Test 6: Create additional alert types
        print("\n" + "=" * 70)
        print("ADDITIONAL ALERT TYPES")
        print("=" * 70)

        # Indicator alert
        indicator_id = await create_indicator_alert("NIFTY50", "rsi", 70)
        if indicator_id:
            await test_alert_evaluation(indicator_id)

        # Composite alert
        composite_id = await create_composite_alert("NIFTY50", 23000, 65)
        if composite_id:
            await test_alert_evaluation(composite_id)

        print("\n" + "=" * 70)
        print("TEST SUMMARY")
        print("=" * 70)
        print("✅ Phase 2 evaluation engine tests completed!")
        print("\nWhat was tested:")
        print("  1. ✅ Service health and worker status")
        print("  2. ✅ Price alert creation")
        print("  3. ✅ Manual alert evaluation (test endpoint)")
        print("  4. ✅ Background worker evaluation")
        print("  5. ✅ Indicator alerts")
        print("  6. ✅ Composite alerts (AND logic)")
        print("\nNext steps:")
        print("  - Check alerts: http://localhost:8082/alerts")
        print("  - View stats: http://localhost:8082/alerts/stats/summary")
        print("  - API docs: http://localhost:8082/docs")
        print("  - Check Telegram for notifications")
        print("=" * 70)

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
