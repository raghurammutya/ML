#!/usr/bin/env python3
"""
Load testing script for TradingView ML Visualization API
Usage: locust -f load_test.py --host=http://localhost:8000 --users=1000 --spawn-rate=50
"""

from locust import HttpUser, task, between
import random
import time
from datetime import datetime, timedelta

class TradingViewUser(HttpUser):
    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks
    
    def on_start(self):
        """Called when a simulated user starts"""
        # Get current time for realistic queries
        self.end_time = int(datetime.now().timestamp())
        self.resolutions = ["1", "5", "15", "30", "60"]
        
    @task(5)
    def view_5min(self):
        """Most common use case - viewing 5-minute chart"""
        self._get_history("5", hours=24)
    
    @task(3)
    def view_15min(self):
        """Viewing 15-minute chart"""
        self._get_history("15", hours=48)
    
    @task(2)
    def view_hourly(self):
        """Viewing hourly chart"""
        self._get_history("60", hours=168)  # 1 week
    
    @task(1)
    def view_daily(self):
        """Viewing daily chart"""
        self._get_history("D", hours=720)  # 30 days
    
    @task(4)
    def get_marks(self):
        """Get ML label marks"""
        resolution = random.choice(self.resolutions)
        start_time = self.end_time - (24 * 3600)  # 24 hours
        
        with self.client.get(
            f"/marks?symbol=NIFTY50&from={start_time}&to={self.end_time}&resolution={resolution}",
            name=f"/marks_{resolution}min",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status {response.status_code}")
    
    @task(2)
    def get_config(self):
        """Get TradingView config"""
        self.client.get("/config", name="/config")
    
    @task(1)
    def search_symbol(self):
        """Search for symbol"""
        self.client.get("/search?query=NIFTY&limit=10", name="/search")
    
    @task(3)
    def check_health(self):
        """Check system health"""
        self.client.get("/health", name="/health")
    
    @task(2)
    def get_cache_stats(self):
        """Get cache statistics"""
        self.client.get("/cache/stats", name="/cache_stats")
    
    def _get_history(self, resolution, hours):
        """Helper to get historical data"""
        start_time = self.end_time - (hours * 3600)
        
        with self.client.get(
            f"/history?symbol=NIFTY50&from={start_time}&to={self.end_time}&resolution={resolution}",
            name=f"/history_{resolution}",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get('s') == 'ok':
                        # Verify data structure
                        required_fields = ['t', 'o', 'h', 'l', 'c', 'v']
                        if all(field in data for field in required_fields):
                            response.success()
                        else:
                            response.failure("Missing required fields")
                    else:
                        response.failure(f"Response status: {data.get('s')}")
                except Exception as e:
                    response.failure(f"Invalid JSON: {e}")
            else:
                response.failure(f"Status {response.status_code}")


class MobileUser(HttpUser):
    """Simulates mobile app users with different behavior"""
    wait_time = between(2, 5)  # Mobile users check less frequently
    
    @task(8)
    def view_5min_mobile(self):
        """Mobile users mostly view 5-min charts"""
        end_time = int(datetime.now().timestamp())
        start_time = end_time - (12 * 3600)  # 12 hours
        
        self.client.get(
            f"/history?symbol=NIFTY50&from={start_time}&to={end_time}&resolution=5",
            name="/history_mobile_5min"
        )
    
    @task(2)
    def check_latest_marks(self):
        """Check latest ML predictions"""
        end_time = int(datetime.now().timestamp())
        start_time = end_time - (3600)  # Last hour
        
        self.client.get(
            f"/marks?symbol=NIFTY50&from={start_time}&to={end_time}&resolution=5",
            name="/marks_mobile"
        )


class APIUser(HttpUser):
    """Simulates programmatic API users"""
    wait_time = between(5, 10)  # API users have rate limits
    
    @task
    def batch_history_requests(self):
        """API users often request multiple timeframes"""
        end_time = int(datetime.now().timestamp())
        resolutions = ["1", "5", "15", "60"]
        
        for resolution in resolutions:
            start_time = end_time - (24 * 3600)
            self.client.get(
                f"/history?symbol=NIFTY50&from={start_time}&to={end_time}&resolution={resolution}",
                name=f"/history_api_{resolution}"
            )
            time.sleep(0.1)  # Slight delay between requests


# Custom shape for load test (gradual ramp-up and sustained load)
def custom_shape(current_time):
    """
    Custom load shape:
    0-60s: Ramp up to 100 users
    60-300s: Sustain 100 users
    300-360s: Ramp up to 1000 users
    360-600s: Sustain 1000 users
    600-660s: Ramp down to 0
    """
    if current_time < 60:
        return int(current_time * 100 / 60)
    elif current_time < 300:
        return 100
    elif current_time < 360:
        return int(100 + (current_time - 300) * 900 / 60)
    elif current_time < 600:
        return 1000
    elif current_time < 660:
        return int(1000 * (660 - current_time) / 60)
    else:
        return 0


if __name__ == "__main__":
    import os
    os.system(
        "locust -f load_test.py "
        "--host=http://5.223.52.98:8888 "
        "--users=100 "
        "--spawn-rate=10 "
        "--run-time=5m "
        "--headless "
        "--print-stats"
    )