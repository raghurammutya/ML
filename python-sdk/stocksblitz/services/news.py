"""
News Service - News alerts and sentiment analysis.

Provides functionality to get news, subscribe to news alerts, and perform
sentiment analysis for ML-based trading decisions.
"""

import uuid
import threading
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta
from collections import defaultdict

from ..enums import NewsCategory, NewsSentiment
from ..types import NewsItem, NewsCallback
from ..exceptions import APIError


class NewsService:
    """
    News and sentiment analysis service.

    Features:
    - Subscribe to news by category/symbol
    - Get news with filters
    - Sentiment analysis (ML-ready)
    - Real-time news alerts
    - News history

    Examples:
        # Get news service
        news = client.news

        # Subscribe to news
        def on_news(item: NewsItem):
            if item.sentiment == NewsSentiment.NEGATIVE:
                print(f"Negative news: {item.title}")

        news.subscribe(
            category=NewsCategory.MARKET,
            callback=on_news
        )

        # Get latest news
        items = news.get_news(
            category=NewsCategory.EARNINGS,
            symbols=["NIFTY50"],
            limit=10
        )

        # Analyze sentiment
        for item in items:
            if item.sentiment_score < -0.5:
                print(f"Strong negative: {item.title}")
    """

    def __init__(self, api_client: 'APIClient'):
        """Initialize news service."""
        self._api = api_client
        self._news_items: Dict[str, NewsItem] = {}
        self._subscribers: Dict[str, List[NewsCallback]] = defaultdict(list)
        self._lock = threading.Lock()
        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None

    def get_news(
        self,
        category: Optional[NewsCategory] = None,
        symbols: Optional[List[str]] = None,
        sentiment: Optional[NewsSentiment] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50
    ) -> List[NewsItem]:
        """
        Get news with filters.

        Args:
            category: Filter by category
            symbols: Filter by symbols
            sentiment: Filter by sentiment
            start_date: Start date
            end_date: End date
            limit: Maximum items to return

        Returns:
            List of news items

        Example:
            # Get market news for NIFTY from last 24 hours
            news_items = news.get_news(
                category=NewsCategory.MARKET,
                symbols=["NIFTY50"],
                start_date=datetime.now() - timedelta(hours=24),
                limit=20
            )
        """
        # TODO: Fetch from API
        # params = {
        #     "category": category.value if category else None,
        #     "symbols": ",".join(symbols) if symbols else None,
        #     "sentiment": sentiment.value if sentiment else None,
        #     "start_date": start_date.isoformat() if start_date else None,
        #     "end_date": end_date.isoformat() if end_date else None,
        #     "limit": limit
        # }
        # response = self._api.get("/news", params=params)
        # return [NewsItem(**item) for item in response.get("data", [])]

        # Return filtered local cache for now
        with self._lock:
            results = list(self._news_items.values())

        if category:
            results = [n for n in results if n.category == category]
        if symbols:
            results = [
                n for n in results
                if any(sym in n.symbols for sym in symbols)
            ]
        if sentiment:
            results = [n for n in results if n.sentiment == sentiment]
        if start_date:
            results = [n for n in results if n.published_at >= start_date]
        if end_date:
            results = [n for n in results if n.published_at <= end_date]

        # Sort by published_at descending
        results.sort(key=lambda x: x.published_at, reverse=True)

        return results[:limit]

    def subscribe(
        self,
        callback: NewsCallback,
        category: Optional[NewsCategory] = None,
        symbols: Optional[List[str]] = None,
        sentiment: Optional[NewsSentiment] = None
    ) -> str:
        """
        Subscribe to news alerts.

        Args:
            callback: Callback function (receives NewsItem)
            category: Filter by category
            symbols: Filter by symbols
            sentiment: Filter by sentiment

        Returns:
            Subscription ID

        Example:
            def handle_earnings(news_item: NewsItem):
                print(f"Earnings news: {news_item.title}")
                if news_item.sentiment_score < -0.5:
                    # Strong negative earnings
                    account.sell(inst, quantity=50)

            sub_id = news.subscribe(
                callback=handle_earnings,
                category=NewsCategory.EARNINGS,
                symbols=["NIFTY50"]
            )
        """
        subscription_id = str(uuid.uuid4())

        # Create filtered callback
        def filtered_callback(item: NewsItem):
            # Apply filters
            if category and item.category != category:
                return
            if symbols and not any(sym in item.symbols for sym in symbols):
                return
            if sentiment and item.sentiment != sentiment:
                return

            # Call user callback
            callback(item)

        with self._lock:
            self._subscribers[subscription_id].append(filtered_callback)

        # TODO: Subscribe via API
        # self._api.post("/news/subscribe", json={
        #     "subscription_id": subscription_id,
        #     "category": category.value if category else None,
        #     "symbols": symbols,
        #     "sentiment": sentiment.value if sentiment else None
        # })

        return subscription_id

    def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe from news alerts.

        Args:
            subscription_id: Subscription ID

        Returns:
            True if unsubscribed, False if not found

        Example:
            news.unsubscribe(sub_id)
        """
        with self._lock:
            if subscription_id in self._subscribers:
                del self._subscribers[subscription_id]
                return True
        return False

        # TODO: Unsubscribe via API
        # self._api.delete(f"/news/subscribe/{subscription_id}")

    def analyze_sentiment(
        self,
        text: str
    ) -> Dict[str, Any]:
        """
        Analyze sentiment of text (ML-based).

        Args:
            text: Text to analyze

        Returns:
            Sentiment analysis result

        Example:
            result = news.analyze_sentiment(
                "Company reports strong earnings, beats expectations"
            )
            # Returns: {
            #     "sentiment": "POSITIVE",
            #     "score": 0.85,
            #     "confidence": 0.92
            # }
        """
        # TODO: Call ML sentiment analysis API
        # response = self._api.post("/news/analyze-sentiment", json={"text": text})
        # return response

        # Stub implementation
        return {
            "sentiment": NewsSentiment.NEUTRAL.value,
            "score": 0.0,
            "confidence": 0.0
        }

    def get_sentiment_summary(
        self,
        symbols: List[str],
        hours: int = 24
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get sentiment summary for symbols.

        Args:
            symbols: List of symbols
            hours: Look back hours

        Returns:
            Sentiment summary by symbol

        Example:
            summary = news.get_sentiment_summary(
                symbols=["NIFTY50", "BANKNIFTY"],
                hours=24
            )
            # Returns: {
            #     "NIFTY50": {
            #         "avg_score": 0.35,
            #         "positive_count": 15,
            #         "negative_count": 5,
            #         "neutral_count": 10
            #     },
            #     ...
            # }
        """
        start_date = datetime.now() - timedelta(hours=hours)
        summary = {}

        for symbol in symbols:
            items = self.get_news(
                symbols=[symbol],
                start_date=start_date
            )

            scores = [
                item.sentiment_score
                for item in items
                if item.sentiment_score is not None
            ]

            summary[symbol] = {
                "avg_score": sum(scores) / len(scores) if scores else 0.0,
                "positive_count": len([
                    i for i in items
                    if i.sentiment == NewsSentiment.POSITIVE
                ]),
                "negative_count": len([
                    i for i in items
                    if i.sentiment == NewsSentiment.NEGATIVE
                ]),
                "neutral_count": len([
                    i for i in items
                    if i.sentiment == NewsSentiment.NEUTRAL
                ]),
                "total_count": len(items)
            }

        return summary

    def _notify_subscribers(self, item: NewsItem) -> None:
        """Notify all subscribers about news item."""
        for callbacks in self._subscribers.values():
            for callback in callbacks:
                try:
                    callback(item)
                except Exception as e:
                    print(f"Error in news callback: {e}")

    def _add_news_item(self, item: NewsItem) -> None:
        """Add news item and notify subscribers."""
        with self._lock:
            self._news_items[item.news_id] = item

        self._notify_subscribers(item)

    def start_monitoring(self) -> None:
        """
        Start background monitoring for news.

        Example:
            news.start_monitoring()
        """
        if self._monitoring:
            return

        self._monitoring = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True
        )
        self._monitor_thread.start()

    def stop_monitoring(self) -> None:
        """Stop background monitoring."""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
            self._monitor_thread = None

    def _monitor_loop(self) -> None:
        """Background monitoring loop for news updates."""
        import time

        while self._monitoring:
            try:
                # TODO: Poll API for new news
                # response = self._api.get("/news/latest")
                # for item_data in response.get("data", []):
                #     item = NewsItem(**item_data)
                #     self._add_news_item(item)

                time.sleep(60)  # Check every minute
            except Exception as e:
                print(f"Error in news monitor: {e}")

    def get_trending_topics(
        self,
        hours: int = 24,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get trending topics/tags.

        Args:
            hours: Look back hours
            limit: Max topics to return

        Returns:
            List of trending topics with counts

        Example:
            trending = news.get_trending_topics(hours=24)
            # Returns: [
            #     {"topic": "earnings", "count": 45},
            #     {"topic": "interest-rate", "count": 32},
            #     ...
            # ]
        """
        start_date = datetime.now() - timedelta(hours=hours)
        items = self.get_news(start_date=start_date)

        # Count tags
        tag_counts = defaultdict(int)
        for item in items:
            for tag in item.tags:
                tag_counts[tag] += 1

        # Sort by count
        trending = [
            {"topic": tag, "count": count}
            for tag, count in sorted(
                tag_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )
        ]

        return trending[:limit]

    def clear_history(self, days: int = 30) -> int:
        """
        Clear old news items.

        Args:
            days: Clear news older than this many days

        Returns:
            Number of items cleared

        Example:
            count = news.clear_history(days=30)
        """
        cutoff = datetime.now() - timedelta(days=days)
        count = 0

        with self._lock:
            to_remove = [
                nid for nid, item in self._news_items.items()
                if item.published_at < cutoff
            ]
            for nid in to_remove:
                del self._news_items[nid]
                count += 1

        return count
