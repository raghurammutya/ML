#!/usr/bin/env python3
"""
StocksBlitz SDK - Services Examples

Demonstrates the four additional services:
1. Alerts Service - Event-based alerts
2. Messaging Service - Pub/sub messaging
3. Calendar Service - Reminders and schedules
4. News Service - News alerts and sentiment analysis

Usage:
    python examples_services.py
"""

from stocksblitz import (
    TradingClient,
    AlertType, AlertPriority, EventStatus,
    MessageType,
    ReminderFrequency,
    NewsCategory, NewsSentiment
)
from datetime import datetime, timedelta
import time


# Configuration
API_URL = "http://localhost:8009"
API_KEY = "sb_30d4d5ea_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6"


def example_1_alert_service():
    """Example 1: Alert Service - Event-based alerts."""
    print("\n" + "="*70)
    print("Example 1: Alert Service")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)
    alerts = client.alerts

    # Register alert callbacks
    def on_price_alert(event):
        print(f"  📍 Price Alert: {event.symbol} - {event.message}")
        print(f"     Priority: {event.priority.value}")
        print(f"     Data: {event.data}")
        event.acknowledge()

    def on_position_alert(event):
        print(f"  💼 Position Alert: {event.message}")
        event.acknowledge()

    # Subscribe to alert types
    alerts.on(AlertType.PRICE, on_price_alert)
    alerts.on(AlertType.POSITION, on_position_alert)
    print("✓ Registered alert callbacks")

    # Raise some alerts
    alert1 = alerts.raise_alert(
        alert_type=AlertType.PRICE,
        priority=AlertPriority.HIGH,
        symbol="NIFTY50",
        message="Price crossed 24000",
        data={"price": 24050, "threshold": 24000}
    )
    print(f"✓ Raised price alert: {alert1.alert_id}")

    alert2 = alerts.raise_alert(
        alert_type=AlertType.POSITION,
        priority=AlertPriority.CRITICAL,
        symbol="BANKNIFTY",
        message="Position PnL below -5%",
        data={"pnl_percent": -5.2, "threshold": -5.0}
    )
    print(f"✓ Raised position alert: {alert2.alert_id}")

    # Query alerts
    high_priority = alerts.get_alerts(priority=AlertPriority.HIGH)
    print(f"\n✓ High priority alerts: {len(high_priority)}")

    triggered_alerts = alerts.get_alerts(status=EventStatus.TRIGGERED)
    print(f"✓ Triggered alerts: {len(triggered_alerts)}")

    # Clear acknowledged alerts
    count = alerts.clear_alerts(status=EventStatus.ACKNOWLEDGED)
    print(f"✓ Cleared {count} acknowledged alerts")


def example_2_conditional_alerts():
    """Example 2: Conditional Alerts (price/indicator based)."""
    print("\n" + "="*70)
    print("Example 2: Conditional Alerts")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)
    alerts = client.alerts

    # Price-based alert
    alert_id = alerts.create_price_alert(
        symbol="NIFTY50",
        condition=lambda price: price > 24000,
        message="NIFTY crossed 24000",
        priority=AlertPriority.HIGH
    )
    print(f"✓ Created price alert: {alert_id}")

    # Indicator-based alert
    alert_id = alerts.create_indicator_alert(
        symbol="NIFTY50",
        timeframe="5m",
        indicator="rsi[14]",
        condition=lambda rsi: rsi > 70,
        message="RSI overbought",
        priority=AlertPriority.MEDIUM
    )
    print(f"✓ Created indicator alert: {alert_id}")

    # Start background monitoring
    # alerts.start_monitoring()
    print("✓ Alert monitoring ready (stub)")


def example_3_messaging_service():
    """Example 3: Messaging Service - Pub/Sub."""
    print("\n" + "="*70)
    print("Example 3: Messaging Service")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)
    messaging = client.messaging

    # Subscribe to topic
    def on_trade_signal(msg):
        print(f"  📨 Trade Signal Received:")
        print(f"     Type: {msg.message_type.value}")
        print(f"     Content: {msg.content}")
        msg.mark_as_read()

    messaging.subscribe("trade-signals", on_trade_signal)
    print("✓ Subscribed to 'trade-signals' topic")

    # Publish messages
    msg1 = messaging.publish(
        topic="trade-signals",
        content={
            "symbol": "NIFTY50",
            "signal": "BUY",
            "price": 24000,
            "reason": "RSI oversold"
        },
        message_type=MessageType.JSON
    )
    print(f"✓ Published trade signal: {msg1.message_id}")

    msg2 = messaging.publish(
        topic="trade-signals",
        content={
            "symbol": "BANKNIFTY",
            "signal": "SELL",
            "price": 51000,
            "reason": "RSI overbought"
        }
    )
    print(f"✓ Published trade signal: {msg2.message_id}")

    # Direct messaging
    direct_msg = messaging.send(
        content="Order #12345 executed",
        recipient="strategy-monitor",
        metadata={"order_id": "12345", "status": "complete"}
    )
    print(f"✓ Sent direct message: {direct_msg.message_id}")

    # Receive messages
    messages = messaging.receive("strategy-monitor")
    print(f"✓ Received {len(messages)} messages")

    # Broadcast
    broadcast = messaging.broadcast({
        "type": "market-alert",
        "message": "Market closing in 30 minutes"
    })
    print(f"✓ Broadcast message: {broadcast.message_id}")


def example_4_calendar_service():
    """Example 4: Calendar Service - Reminders."""
    print("\n" + "="*70)
    print("Example 4: Calendar Service")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)
    calendar = client.calendar

    # One-time reminder
    def close_positions_reminder(reminder):
        print(f"  ⏰ Reminder: {reminder.title}")
        print(f"     {reminder.description}")

    reminder1_id = calendar.set_reminder(
        title="Close positions",
        scheduled_at=datetime.now() + timedelta(hours=6),
        description="Close all positions before market close",
        callback=close_positions_reminder
    )
    print(f"✓ Set one-time reminder: {reminder1_id}")

    # Daily recurring reminder
    def market_open_reminder(reminder):
        print(f"  🔔 Market is opening! Time: {datetime.now()}")

    reminder2_id = calendar.set_recurring_reminder(
        title="Market open",
        frequency=ReminderFrequency.DAILY,
        scheduled_at=datetime.now().replace(hour=9, minute=15),
        callback=market_open_reminder
    )
    print(f"✓ Set daily reminder: {reminder2_id}")

    # Custom interval reminder (every 5 minutes)
    def check_positions_reminder(reminder):
        print("  📊 Checking positions...")

    reminder3_id = calendar.set_recurring_reminder(
        title="Check positions",
        frequency=ReminderFrequency.CUSTOM,
        scheduled_at=datetime.now(),
        metadata={"interval_minutes": 5},
        callback=check_positions_reminder
    )
    print(f"✓ Set custom interval reminder: {reminder3_id}")

    # Get upcoming reminders
    upcoming = calendar.get_upcoming(hours=24)
    print(f"\n✓ Upcoming reminders in next 24h: {len(upcoming)}")
    for reminder in upcoming:
        print(f"   - {reminder.title} ({reminder.frequency.value})")

    # Start monitoring
    # calendar.start_monitoring()
    print("\n✓ Calendar monitoring ready (stub)")


def example_5_news_service():
    """Example 5: News Service - News and Sentiment."""
    print("\n" + "="*70)
    print("Example 5: News Service")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)
    news = client.news

    # Subscribe to news
    def on_earnings_news(item):
        print(f"  📰 Earnings News: {item.title}")
        print(f"     Sentiment: {item.sentiment.value if item.sentiment else 'N/A'}")
        print(f"     Score: {item.sentiment_score}")
        print(f"     Symbols: {', '.join(item.symbols)}")

        # Act on negative earnings
        if item.sentiment == NewsSentiment.NEGATIVE and item.sentiment_score < -0.5:
            print(f"     ⚠️  Strong negative earnings - consider selling")

    sub_id = news.subscribe(
        callback=on_earnings_news,
        category=NewsCategory.EARNINGS,
        symbols=["NIFTY50"]
    )
    print(f"✓ Subscribed to earnings news: {sub_id}")

    # Get latest news
    items = news.get_news(
        category=NewsCategory.MARKET,
        symbols=["NIFTY50", "BANKNIFTY"],
        start_date=datetime.now() - timedelta(hours=24),
        limit=10
    )
    print(f"✓ Retrieved {len(items)} market news items (last 24h)")

    # Analyze sentiment
    result = news.analyze_sentiment(
        "Company reports strong earnings, beats expectations significantly"
    )
    print(f"\n✓ Sentiment Analysis:")
    print(f"   Sentiment: {result['sentiment']}")
    print(f"   Score: {result['score']:.2f}")
    print(f"   Confidence: {result['confidence']:.2f}")

    # Get sentiment summary
    summary = news.get_sentiment_summary(
        symbols=["NIFTY50", "BANKNIFTY"],
        hours=24
    )
    print(f"\n✓ Sentiment Summary (last 24h):")
    for symbol, data in summary.items():
        print(f"   {symbol}:")
        print(f"     Avg Score: {data['avg_score']:.2f}")
        print(f"     Positive: {data['positive_count']}")
        print(f"     Negative: {data['negative_count']}")
        print(f"     Neutral: {data['neutral_count']}")

    # Get trending topics
    trending = news.get_trending_topics(hours=24, limit=5)
    print(f"\n✓ Trending Topics:")
    for topic in trending:
        print(f"   - {topic['topic']}: {topic['count']} mentions")


def example_6_integrated_strategy():
    """Example 6: Integrated Strategy - Using all services."""
    print("\n" + "="*70)
    print("Example 6: Integrated Strategy")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    print("Initializing integrated trading strategy...")
    print("This strategy uses:")
    print("  - Alerts for price/indicator triggers")
    print("  - Messaging for inter-strategy communication")
    print("  - Calendar for scheduled tasks")
    print("  - News for sentiment-based decisions")

    # Setup alerts
    def on_alert(event):
        print(f"\n  🚨 ALERT: {event.message}")
        # Send message to monitoring system
        client.messaging.publish(
            topic="alerts",
            content={
                "alert_id": event.alert_id,
                "symbol": event.symbol,
                "message": event.message,
                "priority": event.priority.value
            }
        )

    client.alerts.on(AlertType.PRICE, on_alert)
    client.alerts.on(AlertType.INDICATOR, on_alert)
    print("✓ Alert handlers configured")

    # Setup news monitoring
    def on_news(item):
        print(f"\n  📰 NEWS: {item.title}")
        # Check sentiment and raise alert if negative
        if item.sentiment == NewsSentiment.NEGATIVE and item.sentiment_score < -0.6:
            client.alerts.raise_alert(
                alert_type=AlertType.CUSTOM,
                priority=AlertPriority.HIGH,
                symbol=item.symbols[0] if item.symbols else None,
                message=f"Strong negative news: {item.title}",
                data={"sentiment_score": item.sentiment_score}
            )

    client.news.subscribe(
        callback=on_news,
        category=NewsCategory.MARKET
    )
    print("✓ News monitoring configured")

    # Setup calendar tasks
    def check_positions():
        print("\n  📊 Scheduled task: Checking positions...")
        # Get positions
        account = client.Account()
        # positions = account.positions
        # ... check positions logic ...

        # Send status update
        client.messaging.publish(
            topic="status",
            content={"task": "position_check", "status": "complete"}
        )

    client.calendar.set_recurring_reminder(
        title="Check positions",
        frequency=ReminderFrequency.CUSTOM,
        scheduled_at=datetime.now(),
        metadata={"interval_minutes": 15},
        callback=check_positions
    )
    print("✓ Calendar tasks scheduled")

    print("\n✓ Integrated strategy ready!")
    print("  Strategy will:")
    print("  1. Monitor price/indicator alerts")
    print("  2. Track news sentiment")
    print("  3. Run scheduled position checks")
    print("  4. Communicate via messaging system")


def example_7_error_handling():
    """Example 7: Error Handling with Services."""
    print("\n" + "="*70)
    print("Example 7: Error Handling")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    # Alert error handling
    try:
        alert = client.alerts.raise_alert(
            alert_type=AlertType.PRICE,
            priority=AlertPriority.HIGH,
            symbol="NIFTY50",
            message="Test alert"
        )
        print(f"✓ Alert raised: {alert.alert_id}")
    except Exception as e:
        print(f"❌ Alert error: {e}")

    # Messaging error handling
    try:
        msg = client.messaging.publish(
            topic="test",
            content={"test": "data"}
        )
        print(f"✓ Message published: {msg.message_id}")
    except Exception as e:
        print(f"❌ Messaging error: {e}")

    # Calendar error handling
    try:
        reminder_id = client.calendar.set_reminder(
            title="Test",
            scheduled_at=datetime.now() + timedelta(hours=1)
        )
        print(f"✓ Reminder set: {reminder_id}")
    except Exception as e:
        print(f"❌ Calendar error: {e}")

    # News error handling
    try:
        items = client.news.get_news(limit=5)
        print(f"✓ Retrieved {len(items)} news items")
    except Exception as e:
        print(f"❌ News error: {e}")


def example_8_type_safety():
    """Example 8: Type Safety with Enums."""
    print("\n" + "="*70)
    print("Example 8: Type Safety with Enums")
    print("="*70)

    client = TradingClient(api_url=API_URL, api_key=API_KEY)

    # Using enums for type safety
    print("Using enums for type-safe code:")

    # Alert with enums
    alert = client.alerts.raise_alert(
        alert_type=AlertType.PRICE,  # Type-safe
        priority=AlertPriority.CRITICAL,  # Type-safe
        symbol="NIFTY50",
        message="Critical price alert"
    )
    print(f"✓ Alert type: {alert.alert_type.value}")
    print(f"✓ Priority: {alert.priority.value}")
    print(f"✓ Status: {alert.status.value}")

    # Message with enums
    msg = client.messaging.send(
        content="Test message",
        message_type=MessageType.TEXT  # Type-safe
    )
    print(f"✓ Message type: {msg.message_type.value}")

    # Calendar with enums
    reminder_id = client.calendar.set_recurring_reminder(
        title="Daily task",
        frequency=ReminderFrequency.DAILY,  # Type-safe
        scheduled_at=datetime.now()
    )
    print(f"✓ Reminder frequency: {ReminderFrequency.DAILY.value}")

    # News with enums
    def on_news(item):
        print(f"  Category: {item.category.value}")  # Type-safe
        print(f"  Sentiment: {item.sentiment.value if item.sentiment else 'N/A'}")

    client.news.subscribe(
        callback=on_news,
        category=NewsCategory.EARNINGS,  # Type-safe
        sentiment=NewsSentiment.POSITIVE  # Type-safe
    )
    print("✓ News subscription configured with type-safe enums")


def main():
    """Run all service examples."""
    print("\n" + "#"*70)
    print("# StocksBlitz SDK - Services Examples")
    print("#"*70)

    examples = [
        example_1_alert_service,
        example_2_conditional_alerts,
        example_3_messaging_service,
        example_4_calendar_service,
        example_5_news_service,
        example_6_integrated_strategy,
        example_7_error_handling,
        example_8_type_safety,
    ]

    for example in examples:
        try:
            example()
            time.sleep(1)  # Brief pause between examples
        except Exception as e:
            print(f"\n  ❌ Error in {example.__name__}: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "="*70)
    print("All service examples completed!")
    print("="*70)
    print("\nNote: Some features are stubs and will be fully")
    print("implemented when backend services are available.")
    print("="*70)


if __name__ == "__main__":
    main()
