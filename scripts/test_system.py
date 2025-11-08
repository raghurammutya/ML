#!/usr/bin/env python3
"""
System test script to verify the TradingView ML Visualization setup
"""

import asyncio
import httpx
import json
from datetime import datetime, timedelta

async def test_backend():
    """Test backend endpoints"""
    base_url = "http://5.223.52.98:8888"
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        print("Testing Backend API...")
        print("-" * 50)
        
        # Test health endpoint
        try:
            response = await client.get(f"{base_url}/health")
            print(f"✓ Health Check: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"  Status: {data['status']}")
                print(f"  Database: {data['database']}")
                print(f"  Redis: {data['redis']}")
        except Exception as e:
            print(f"✗ Health Check failed: {e}")
        
        # Test config endpoint
        try:
            response = await client.get(f"{base_url}/config")
            print(f"✓ Config: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"  Supported resolutions: {data['supported_resolutions']}")
        except Exception as e:
            print(f"✗ Config failed: {e}")
        
        # Test history endpoint
        try:
            end_time = int(datetime.now().timestamp())
            start_time = end_time - 3600  # 1 hour ago
            
            response = await client.get(
                f"{base_url}/history?symbol=NIFTY50&from={start_time}&to={end_time}&resolution=5"
            )
            print(f"✓ History: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                if data['s'] == 'ok':
                    print(f"  Data points: {len(data.get('t', []))}")
                    if data.get('c'):
                        print(f"  Latest price: ₹{data['c'][-1]}")
        except Exception as e:
            print(f"✗ History failed: {e}")
        
        print("\nCache Performance Test...")
        print("-" * 50)
        
        # Test cache performance
        import time
        
        # First call (cache miss)
        start = time.time()
        response = await client.get(
            f"{base_url}/history?symbol=NIFTY50&from={start_time}&to={end_time}&resolution=5"
        )
        first_call_time = (time.time() - start) * 1000
        
        # Second call (should be cached)
        start = time.time()
        response = await client.get(
            f"{base_url}/history?symbol=NIFTY50&from={start_time}&to={end_time}&resolution=5"
        )
        cached_call_time = (time.time() - start) * 1000
        
        print(f"First call: {first_call_time:.2f}ms")
        print(f"Cached call: {cached_call_time:.2f}ms")
        print(f"Speedup: {first_call_time/cached_call_time:.1f}x")
        
        # Check cache stats
        response = await client.get(f"{base_url}/cache/stats")
        if response.status_code == 200:
            stats = response.json()
            print(f"\nCache Statistics:")
            print(f"  Hit rate: {stats.get('hit_rate', 0):.1f}%")
            print(f"  L1 hits: {stats.get('l1_hits', 0)}")
            print(f"  L2 hits: {stats.get('l2_hits', 0)}")
            print(f"  Total misses: {stats.get('total_misses', 0)}")

if __name__ == "__main__":
    print("TradingView ML Visualization System Test")
    print("=" * 50)
    asyncio.run(test_backend())