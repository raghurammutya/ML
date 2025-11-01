#!/usr/bin/env python3
"""
Calendar Service - Comprehensive Test Suite
Tests all endpoints, validation, error handling, and performance

Usage:
    python test_calendar_service.py
    python test_calendar_service.py --verbose
    python test_calendar_service.py --load-test
"""

import asyncio
import sys
import time
import argparse
from datetime import date, timedelta
from typing import List, Tuple
import httpx

# Configuration
BASE_URL = "http://localhost:8081"
TIMEOUT = 10.0

# ANSI Colors
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

class TestRunner:
    def __init__(self, verbose=False):
        self.verbose = verbose
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.tests_run = []

    def log(self, message, level="INFO"):
        colors = {
            "INFO": Colors.BLUE,
            "PASS": Colors.GREEN,
            "FAIL": Colors.RED,
            "WARN": Colors.YELLOW
        }
        color = colors.get(level, "")
        print(f"{color}{level}{Colors.END}: {message}")

    def assert_equal(self, actual, expected, test_name):
        if actual == expected:
            self.passed += 1
            self.log(f"✓ {test_name}", "PASS")
            return True
        else:
            self.failed += 1
            self.log(f"✗ {test_name}: Expected {expected}, got {actual}", "FAIL")
            return False

    def assert_status(self, response, expected_status, test_name):
        if response.status_code == expected_status:
            self.passed += 1
            self.log(f"✓ {test_name} (HTTP {response.status_code})", "PASS")
            return True
        else:
            self.failed += 1
            self.log(f"✗ {test_name}: Expected HTTP {expected_status}, got {response.status_code}", "FAIL")
            if self.verbose and response.text:
                print(f"   Response: {response.text[:200]}")
            return False

    async def run_all_tests(self, load_test=False):
        """Run all test suites"""
        print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
        print(f"{Colors.BOLD}CALENDAR SERVICE - COMPREHENSIVE TEST SUITE{Colors.END}")
        print(f"{Colors.BOLD}{'='*70}{Colors.END}\n")

        async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
            # Test Suite 1: Health & Availability
            await self.test_health_endpoint(client)

            # Test Suite 2: Input Validation
            await self.test_input_validation(client)

            # Test Suite 3: Core Functionality
            await self.test_core_functionality(client)

            # Test Suite 4: Error Handling
            await self.test_error_handling(client)

            # Test Suite 5: Performance
            await self.test_performance(client)

            # Test Suite 6: Load Testing (optional)
            if load_test:
                await self.test_load(client)

        # Print Summary
        self.print_summary()

    async def test_health_endpoint(self, client):
        """Test health check endpoint"""
        print(f"\n{Colors.BOLD}[1] Health & Availability Tests{Colors.END}")
        print("-" * 70)

        # Test 1: Health endpoint exists
        try:
            response = await client.get("/calendar/health")
            self.assert_status(response, 200, "Health endpoint accessible")

            if response.status_code == 200:
                data = response.json()
                self.assert_equal(data.get("status"), "healthy", "Health status is 'healthy'")
                self.assert_equal(data.get("database"), "connected", "Database is connected")
                if data.get("calendars_available", 0) > 0:
                    self.passed += 1
                    self.log(f"✓ Calendars available: {data['calendars_available']}", "PASS")
                else:
                    self.failed += 1
                    self.log("✗ No calendars available", "FAIL")
        except Exception as e:
            self.failed += 1
            self.log(f"✗ Health endpoint error: {e}", "FAIL")

    async def test_input_validation(self, client):
        """Test input validation"""
        print(f"\n{Colors.BOLD}[2] Input Validation Tests{Colors.END}")
        print("-" * 70)

        # Test 1: Invalid calendar code
        response = await client.get("/calendar/status?calendar=INVALID")
        self.assert_status(response, 404, "Invalid calendar code rejected")

        # Test 2: Invalid year (too high)
        response = await client.get("/calendar/holidays?calendar=NSE&year=2050")
        self.assert_status(response, 400, "Year 2050 rejected (out of range)")

        # Test 3: Invalid year (too low)
        response = await client.get("/calendar/holidays?calendar=NSE&year=2010")
        self.assert_status(response, 400, "Year 2010 rejected (out of range)")

        # Test 4: Invalid date (too far future)
        response = await client.get("/calendar/status?calendar=NSE&check_date=2099-12-31")
        self.assert_status(response, 400, "Date 2099-12-31 rejected (out of range)")

        # Test 5: Valid calendar codes
        valid_calendars = ["NSE", "BSE", "MCX", "NCDEX"]
        for cal in valid_calendars:
            response = await client.get(f"/calendar/status?calendar={cal}")
            self.assert_status(response, 200, f"Valid calendar '{cal}' accepted")

    async def test_core_functionality(self, client):
        """Test core functionality"""
        print(f"\n{Colors.BOLD}[3] Core Functionality Tests{Colors.END}")
        print("-" * 70)

        # Test 1: Get market status
        response = await client.get("/calendar/status?calendar=NSE")
        if self.assert_status(response, 200, "Get market status"):
            data = response.json()
            required_fields = ["calendar_code", "date", "is_trading_day", "is_holiday",
                             "is_weekend", "current_session"]
            for field in required_fields:
                if field in data:
                    self.passed += 1
                    if self.verbose:
                        self.log(f"✓ Field '{field}' present", "PASS")
                else:
                    self.failed += 1
                    self.log(f"✗ Field '{field}' missing", "FAIL")

        # Test 2: Get holidays for 2025
        response = await client.get("/calendar/holidays?calendar=NSE&year=2025")
        if self.assert_status(response, 200, "Get holidays for 2025"):
            holidays = response.json()
            if len(holidays) > 0:
                self.passed += 1
                self.log(f"✓ Found {len(holidays)} holidays for 2025", "PASS")
            else:
                self.warnings += 1
                self.log("⚠ No holidays found for 2025", "WARN")

        # Test 3: Get next trading day
        response = await client.get("/calendar/next-trading-day?calendar=NSE")
        if self.assert_status(response, 200, "Get next trading day"):
            data = response.json()
            if "next_trading_day" in data:
                self.passed += 1
                self.log(f"✓ Next trading day: {data['next_trading_day']}", "PASS")

        # Test 4: List calendars
        response = await client.get("/calendar/calendars")
        if self.assert_status(response, 200, "List calendars"):
            calendars = response.json()
            if len(calendars) >= 6:  # Expect at least NSE, BSE, MCX, NCDEX, NSE_CURRENCY, BSE_CURRENCY
                self.passed += 1
                self.log(f"✓ Found {len(calendars)} calendars", "PASS")
            else:
                self.failed += 1
                self.log(f"✗ Expected at least 6 calendars, got {len(calendars)}", "FAIL")

    async def test_error_handling(self, client):
        """Test error handling"""
        print(f"\n{Colors.BOLD}[4] Error Handling Tests{Colors.END}")
        print("-" * 70)

        # Test 1: Invalid calendar with helpful error message
        response = await client.get("/calendar/status?calendar=INVALID")
        if response.status_code == 404:
            data = response.json()
            if "detail" in data and "Valid calendars:" in data["detail"]:
                self.passed += 1
                self.log("✓ Invalid calendar error includes valid calendars list", "PASS")
            else:
                self.failed += 1
                self.log("✗ Invalid calendar error missing helpful message", "FAIL")

        # Test 2: No trading day found error
        far_future = date.today() + timedelta(days=100)
        response = await client.get(f"/calendar/next-trading-day?calendar=NSE&after_date={far_future}")
        # Should either return 200 with a day or 404 if none found
        if response.status_code in [200, 404]:
            self.passed += 1
            self.log("✓ Next trading day handles far future dates", "PASS")

    async def test_performance(self, client):
        """Test performance"""
        print(f"\n{Colors.BOLD}[5] Performance Tests{Colors.END}")
        print("-" * 70)

        # Test 1: Response time < 100ms
        tests = [
            ("/calendar/health", "Health endpoint"),
            ("/calendar/status?calendar=NSE", "Market status"),
            ("/calendar/calendars", "List calendars"),
        ]

        for endpoint, name in tests:
            start = time.time()
            response = await client.get(endpoint)
            duration_ms = (time.time() - start) * 1000

            if response.status_code == 200 and duration_ms < 100:
                self.passed += 1
                self.log(f"✓ {name}: {duration_ms:.1f}ms < 100ms", "PASS")
            elif response.status_code == 200:
                self.warnings += 1
                self.log(f"⚠ {name}: {duration_ms:.1f}ms (slow)", "WARN")
            else:
                self.failed += 1
                self.log(f"✗ {name}: Failed (HTTP {response.status_code})", "FAIL")

        # Test 2: Concurrent requests
        print("\n  Testing concurrent requests...")
        start = time.time()
        tasks = [client.get("/calendar/status?calendar=NSE") for _ in range(10)]
        responses = await asyncio.gather(*tasks)
        duration = time.time() - start

        success_count = sum(1 for r in responses if r.status_code == 200)
        if success_count == 10:
            self.passed += 1
            self.log(f"✓ 10 concurrent requests in {duration:.2f}s", "PASS")
        else:
            self.failed += 1
            self.log(f"✗ Only {success_count}/10 concurrent requests succeeded", "FAIL")

    async def test_load(self, client):
        """Load testing (optional)"""
        print(f"\n{Colors.BOLD}[6] Load Testing{Colors.END}")
        print("-" * 70)

        # Test: 100 requests
        print("  Running 100 requests...")
        start = time.time()
        tasks = [client.get("/calendar/status?calendar=NSE") for _ in range(100)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        duration = time.time() - start

        success_count = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code == 200)
        error_count = sum(1 for r in responses if isinstance(r, Exception))

        self.log(f"  Completed: {success_count}/100 successful, {error_count} errors", "INFO")
        self.log(f"  Duration: {duration:.2f}s", "INFO")
        self.log(f"  Rate: {100/duration:.1f} req/s", "INFO")

        if success_count >= 95:
            self.passed += 1
            self.log("✓ Load test passed (≥95% success rate)", "PASS")
        else:
            self.failed += 1
            self.log(f"✗ Load test failed ({success_count}% success rate)", "FAIL")

    def print_summary(self):
        """Print test summary"""
        print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
        print(f"{Colors.BOLD}TEST SUMMARY{Colors.END}")
        print(f"{Colors.BOLD}{'='*70}{Colors.END}")

        total = self.passed + self.failed
        pass_rate = (self.passed / total * 100) if total > 0 else 0

        print(f"\n  {Colors.GREEN}✓ Passed:{Colors.END}   {self.passed}")
        print(f"  {Colors.RED}✗ Failed:{Colors.END}   {self.failed}")
        if self.warnings > 0:
            print(f"  {Colors.YELLOW}⚠ Warnings:{Colors.END} {self.warnings}")
        print(f"  {Colors.BOLD}Pass Rate:{Colors.END} {pass_rate:.1f}%\n")

        if self.failed == 0:
            print(f"{Colors.GREEN}{Colors.BOLD}✅ ALL TESTS PASSED - PRODUCTION READY{Colors.END}\n")
            return 0
        elif pass_rate >= 90:
            print(f"{Colors.YELLOW}{Colors.BOLD}⚠️  MOSTLY PASSING - REVIEW FAILURES{Colors.END}\n")
            return 1
        else:
            print(f"{Colors.RED}{Colors.BOLD}❌ MULTIPLE FAILURES - NOT PRODUCTION READY{Colors.END}\n")
            return 2


async def main():
    parser = argparse.ArgumentParser(description="Calendar Service Test Suite")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--load-test", "-l", action="store_true", help="Run load tests")
    args = parser.parse_args()

    runner = TestRunner(verbose=args.verbose)
    await runner.run_all_tests(load_test=args.load_test)
    sys.exit(runner.print_summary())


if __name__ == "__main__":
    asyncio.run(main())
