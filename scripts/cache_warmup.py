#!/usr/bin/env python3
"""
Cache warmup script for TradingView ML Visualization API
Preloads frequently accessed data into cache for optimal performance
"""

import asyncio
import httpx
from datetime import datetime, timedelta
import sys
import json
import argparse

class CacheWarmer:
    def __init__(self, base_url="http://5.223.52.98:8888"):
        self.base_url = base_url
        self.client = None
        self.stats = {
            "total_requests": 0,
            "successful": 0,
            "failed": 0,
            "duration": 0
        }
    
    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=30.0, limits=httpx.Limits(max_connections=20))
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
    
    async def warmup_history(self, resolution, days_back, chunk_hours=24):
        """Warmup historical data for a specific resolution"""
        end_time = int(datetime.now().timestamp())
        tasks = []
        
        print(f"Warming up {resolution} resolution for {days_back} days...")
        
        for day in range(days_back):
            # Calculate time range for this chunk
            chunk_end = end_time - (day * 86400)
            chunk_start = chunk_end - (chunk_hours * 3600)
            
            url = f"{self.base_url}/history?symbol=NIFTY50&from={chunk_start}&to={chunk_end}&resolution={resolution}"
            tasks.append(self._fetch_url(url, f"history_{resolution}_{day}"))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results
    
    async def warmup_marks(self, resolution, days_back):
        """Warmup ML marks/labels for a specific resolution"""
        end_time = int(datetime.now().timestamp())
        tasks = []
        
        print(f"Warming up marks for {resolution} resolution...")
        
        for day in range(days_back):
            chunk_end = end_time - (day * 86400)
            chunk_start = chunk_end - 86400
            
            # Regular marks
            url = f"{self.base_url}/marks?symbol=NIFTY50&from={chunk_start}&to={chunk_end}&resolution={resolution}"
            tasks.append(self._fetch_url(url, f"marks_{resolution}_{day}"))
            
            # Timescale marks
            url = f"{self.base_url}/timescale_marks?symbol=NIFTY50&from={chunk_start}&to={chunk_end}&resolution={resolution}"
            tasks.append(self._fetch_url(url, f"timescale_marks_{resolution}_{day}"))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results
    
    async def _fetch_url(self, url, name):
        """Fetch a single URL and track statistics"""
        self.stats["total_requests"] += 1
        
        try:
            start_time = asyncio.get_event_loop().time()
            response = await self.client.get(url)
            duration = asyncio.get_event_loop().time() - start_time
            
            if response.status_code == 200:
                self.stats["successful"] += 1
                print(f" {name} - {duration:.2f}s")
                return {"url": url, "status": "success", "duration": duration}
            else:
                self.stats["failed"] += 1
                print(f" {name} - Status {response.status_code}")
                return {"url": url, "status": "failed", "error": f"Status {response.status_code}"}
        
        except Exception as e:
            self.stats["failed"] += 1
            print(f" {name} - Error: {e}")
            return {"url": url, "status": "error", "error": str(e)}
    
    async def warmup_all(self, resolutions=None, days_back=None):
        """Warmup all configured resolutions and time periods"""
        if resolutions is None:
            resolutions = ["1", "5", "15", "30", "60"]
        
        if days_back is None:
            days_back = {
                "1": 3,    # 3 days of 1-minute data
                "5": 7,    # 7 days of 5-minute data
                "15": 14,  # 14 days of 15-minute data
                "30": 30,  # 30 days of 30-minute data
                "60": 60   # 60 days of hourly data
            }
        
        start_time = asyncio.get_event_loop().time()
        
        # First, warmup static endpoints
        print("Warming up static endpoints...")
        static_urls = [
            f"{self.base_url}/config",
            f"{self.base_url}/symbols?symbol=NIFTY50",
            f"{self.base_url}/search?query=NIFTY",
            f"{self.base_url}/time",
            f"{self.base_url}/health"
        ]
        
        static_tasks = [self._fetch_url(url, url.split('/')[-1]) for url in static_urls]
        await asyncio.gather(*static_tasks)
        
        # Warmup historical data and marks
        print("\nWarming up historical data and marks...")
        all_tasks = []
        
        for resolution in resolutions:
            days = days_back.get(resolution, 7)
            
            # History data
            history_results = await self.warmup_history(resolution, days)
            
            # ML marks
            marks_results = await self.warmup_marks(resolution, days)
            
            all_tasks.extend(history_results)
            all_tasks.extend(marks_results)
        
        # Calculate total duration
        self.stats["duration"] = asyncio.get_event_loop().time() - start_time
        
        return all_tasks
    
    async def verify_cache(self):
        """Verify cache is working by checking cache stats"""
        try:
            response = await self.client.get(f"{self.base_url}/cache/stats")
            if response.status_code == 200:
                stats = response.json()
                return stats
        except Exception as e:
            print(f"Error fetching cache stats: {e}")
            return None
    
    def print_summary(self):
        """Print warmup summary"""
        print("\n" + "="*60)
        print("Cache Warmup Summary")
        print("="*60)
        print(f"Total Requests: {self.stats['total_requests']}")
        print(f"Successful: {self.stats['successful']}")
        print(f"Failed: {self.stats['failed']}")
        print(f"Success Rate: {(self.stats['successful'] / max(self.stats['total_requests'], 1) * 100):.1f}%")
        print(f"Total Duration: {self.stats['duration']:.2f}s")
        print(f"Avg Request Time: {(self.stats['duration'] / max(self.stats['total_requests'], 1)):.3f}s")


async def main():
    parser = argparse.ArgumentParser(description="Warmup cache for TradingView ML Visualization API")
    parser.add_argument("--url", default="http://5.223.52.98:8888", help="Base URL of the API")
    parser.add_argument("--resolutions", nargs="+", default=["1", "5", "15", "30", "60"], 
                        help="Resolutions to warmup")
    parser.add_argument("--days", type=int, help="Number of days to warmup (applies to all resolutions)")
    parser.add_argument("--verify", action="store_true", help="Verify cache after warmup")
    
    args = parser.parse_args()
    
    # Prepare days_back configuration
    days_back = None
    if args.days:
        days_back = {res: args.days for res in args.resolutions}
    
    print(f"Starting cache warmup for {args.url}")
    print(f"Resolutions: {', '.join(args.resolutions)}")
    print("")
    
    async with CacheWarmer(args.url) as warmer:
        # Run warmup
        await warmer.warmup_all(resolutions=args.resolutions, days_back=days_back)
        
        # Print summary
        warmer.print_summary()
        
        # Verify cache if requested
        if args.verify:
            print("\nVerifying cache...")
            cache_stats = await warmer.verify_cache()
            if cache_stats:
                print(f"\nCache Statistics:")
                print(f"L1 Hits: {cache_stats.get('l1_hits', 0)}")
                print(f"L2 Hits: {cache_stats.get('l2_hits', 0)}")
                print(f"Total Misses: {cache_stats.get('total_misses', 0)}")
                print(f"Hit Rate: {cache_stats.get('hit_rate', 0):.1f}%")
                print(f"Memory Cache Size: {cache_stats.get('memory_cache_size', 0)}")
                print(f"Redis Keys: {cache_stats.get('redis_keys', 0)}")


if __name__ == "__main__":
    asyncio.run(main())