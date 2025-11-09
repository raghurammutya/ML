"""
Locust load testing file for TradingView Backend API.

Usage:
    # Web UI mode (recommended for interactive testing)
    locust -f tests/load/locustfile.py --host=http://localhost:8000
    # Then open http://localhost:8089 in browser

    # Headless mode (for CI/CD)
    locust -f tests/load/locustfile.py --host=http://localhost:8000 \
           --users 100 --spawn-rate 10 --run-time 1m --headless

    # Specific user class
    locust -f tests/load/locustfile.py --host=http://localhost:8000 \
           WebSocketUser --users 50 --spawn-rate 5

Test Scenarios:
    - ReadOnlyUser: Health checks and instrument queries
    - APIUser: Full CRUD operations (funds, strategies)
    - WebSocketUser: WebSocket connections and streaming
    - MixedWorkloadUser: Realistic mix of operations
"""
from locust import HttpUser, task, between, constant, events
from locust.contrib.fasthttp import FastHttpUser
import json
import random
from datetime import datetime, date, timedelta


class ReadOnlyUser(FastHttpUser):
    """
    Read-only operations user.
    Simulates users browsing instruments and checking system health.
    """
    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks

    @task(10)
    def health_check(self):
        """Health endpoint (high frequency)."""
        self.client.get("/health")

    @task(5)
    def list_instruments(self):
        """List instruments with pagination."""
        params = {
            "limit": random.choice([10, 50, 100]),
            "offset": random.randint(0, 200)
        }
        self.client.get("/instruments", params=params)

    @task(3)
    def fo_enabled_instruments(self):
        """Get F&O enabled instruments."""
        params = {
            "limit": random.choice([10, 50]),
            "offset": random.randint(0, 100)
        }
        self.client.get("/instruments/fo-enabled", params=params)

    @task(2)
    def search_instruments(self):
        """Search instruments by symbol."""
        symbols = ["NIFTY", "BANKNIFTY", "RELIANCE", "INFY", "TCS"]
        symbol = random.choice(symbols)
        params = {"q": symbol, "limit": 20}
        self.client.get(f"/instruments/search", params=params)

    @task(1)
    def get_instrument_by_token(self):
        """Get specific instrument by token."""
        # Sample instrument tokens (you may want to update these)
        tokens = [256265, 260105, 738561, 492033]
        token = random.choice(tokens)
        self.client.get(f"/instruments/{token}")


class APIUser(FastHttpUser):
    """
    API operations user.
    Simulates users performing CRUD operations on funds and strategies.
    """
    wait_time = between(2, 5)

    def on_start(self):
        """Setup: Create test account ID."""
        self.account_id = f"test_account_{random.randint(1000, 9999)}"

    @task(5)
    def get_funds_uploads(self):
        """Get statement uploads for account."""
        params = {"account_id": self.account_id, "limit": 10}
        self.client.get("/funds/uploads", params=params)

    @task(3)
    def get_category_summary(self):
        """Get funds category summary."""
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        params = {
            "account_id": self.account_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        }
        self.client.get("/funds/category-summary", params=params)

    @task(2)
    def list_strategies(self):
        """List trading strategies."""
        params = {"account_id": self.account_id, "limit": 20}
        self.client.get("/strategies", params=params)

    @task(1)
    def validate_order(self):
        """Validate smart order."""
        payload = {
            "instrument_token": 256265,
            "quantity": random.choice([50, 75, 100]),
            "price": round(random.uniform(19000, 20000), 2),
            "transaction_type": random.choice(["BUY", "SELL"]),
            "product": random.choice(["MIS", "CNC", "NRML"]),
            "order_type": "LIMIT"
        }
        self.client.post(
            "/smart-orders/validate",
            json=payload,
            headers={"Content-Type": "application/json"}
        )

    @task(1)
    def cost_breakdown(self):
        """Calculate order cost breakdown."""
        payload = {
            "instrument_token": random.choice([256265, 260105]),
            "quantity": random.choice([50, 100]),
            "price": round(random.uniform(19000, 20000), 2),
            "transaction_type": random.choice(["BUY", "SELL"]),
            "product": random.choice(["MIS", "CNC"]),
            "segment": random.choice(["equity", "fno"])
        }
        self.client.post(
            "/smart-orders/cost-breakdown",
            json=payload,
            headers={"Content-Type": "application/json"}
        )


class UDFUser(FastHttpUser):
    """
    UDF (TradingView Chart) operations user.
    Simulates TradingView chart data requests.
    """
    wait_time = between(1, 2)

    @task(5)
    def udf_config(self):
        """Get UDF configuration."""
        self.client.get("/udf/config")

    @task(3)
    def udf_symbols(self):
        """Search symbols for UDF."""
        symbols = ["NIFTY50", "BANKNIFTY", "RELIANCE", "INFY"]
        symbol = random.choice(symbols)
        params = {"symbol": symbol}
        self.client.get("/udf/symbols", params=params)

    @task(2)
    def udf_history(self):
        """Get historical data for UDF."""
        symbols = ["NSE:NIFTY50", "NSE:BANKNIFTY"]
        symbol = random.choice(symbols)
        end_time = int(datetime.now().timestamp())
        start_time = end_time - (86400 * 7)  # 7 days ago

        params = {
            "symbol": symbol,
            "resolution": random.choice(["1", "5", "15", "60", "D"]),
            "from": start_time,
            "to": end_time
        }
        self.client.get("/udf/history", params=params)


class FOAnalysisUser(FastHttpUser):
    """
    F&O Analysis user.
    Simulates users querying F&O analysis endpoints.
    """
    wait_time = between(2, 4)

    @task(5)
    def moneyness_series(self):
        """Get moneyness series data."""
        params = {
            "symbol": random.choice(["NIFTY50", "BANKNIFTY"]),
            "timeframe": random.choice(["1min", "5min", "15min"]),
            "indicator": random.choice(["iv", "delta", "gamma", "oi"]),
            "hours": random.choice([1, 3, 6])
        }
        self.client.get("/fo/moneyness-series", params=params)

    @task(3)
    def chain_snapshot(self):
        """Get option chain snapshot."""
        params = {
            "symbol": random.choice(["NIFTY50", "BANKNIFTY"]),
            "expiry": None  # Current expiry
        }
        self.client.get("/fo/chain-snapshot", params=params)

    @task(2)
    def strike_analytics(self):
        """Get strike-level analytics."""
        params = {
            "symbol": random.choice(["NIFTY50", "BANKNIFTY"]),
            "strike": random.choice([19000, 19500, 20000]),
            "expiry": None
        }
        self.client.get("/fo/strike-analytics", params=params)


class MixedWorkloadUser(FastHttpUser):
    """
    Mixed workload user.
    Realistic mix of operations weighted by typical usage patterns.
    """
    wait_time = between(1, 5)

    def on_start(self):
        """Setup: Create test account ID."""
        self.account_id = f"test_account_{random.randint(1000, 9999)}"

    # Health checks (very frequent)
    @task(20)
    def health_check(self):
        self.client.get("/health")

    # Instrument queries (frequent)
    @task(10)
    def list_instruments(self):
        params = {"limit": random.choice([10, 50]), "offset": random.randint(0, 100)}
        self.client.get("/instruments", params=params)

    # UDF requests (frequent for chart users)
    @task(8)
    def udf_history(self):
        symbols = ["NSE:NIFTY50", "NSE:BANKNIFTY"]
        symbol = random.choice(symbols)
        end_time = int(datetime.now().timestamp())
        start_time = end_time - (86400 * 7)

        params = {
            "symbol": symbol,
            "resolution": random.choice(["5", "15", "60"]),
            "from": start_time,
            "to": end_time
        }
        self.client.get("/udf/history", params=params)

    # F&O analysis (moderate)
    @task(5)
    def moneyness_series(self):
        params = {
            "symbol": random.choice(["NIFTY50", "BANKNIFTY"]),
            "timeframe": "5min",
            "indicator": random.choice(["iv", "delta", "oi"]),
            "hours": 3
        }
        self.client.get("/fo/moneyness-series", params=params)

    # Funds queries (moderate)
    @task(3)
    def get_category_summary(self):
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        params = {
            "account_id": self.account_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        }
        self.client.get("/funds/category-summary", params=params)

    # Order validation (less frequent)
    @task(2)
    def validate_order(self):
        payload = {
            "instrument_token": 256265,
            "quantity": random.choice([50, 100]),
            "price": round(random.uniform(19000, 20000), 2),
            "transaction_type": random.choice(["BUY", "SELL"]),
            "product": random.choice(["MIS", "CNC"]),
            "order_type": "LIMIT"
        }
        self.client.post("/smart-orders/validate", json=payload)

    # Strategy queries (occasional)
    @task(1)
    def list_strategies(self):
        params = {"account_id": self.account_id, "limit": 20}
        self.client.get("/strategies", params=params)


# Event handlers for custom metrics
@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """Track custom metrics per request."""
    if exception:
        print(f"Request failed: {name} - {exception}")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Print test start message."""
    print(f"\n{'='*60}")
    print(f"Starting load test at {datetime.now()}")
    print(f"Target host: {environment.host}")
    print(f"{'='*60}\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Print test summary."""
    print(f"\n{'='*60}")
    print(f"Load test completed at {datetime.now()}")
    print(f"Total requests: {environment.stats.total.num_requests}")
    print(f"Total failures: {environment.stats.total.num_failures}")
    print(f"Average response time: {environment.stats.total.avg_response_time:.2f}ms")
    print(f"RPS: {environment.stats.total.total_rps:.2f}")
    print(f"{'='*60}\n")
