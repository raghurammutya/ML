"""
Query Profiling Utilities for N+1 Detection

This module provides utilities to detect and profile database queries,
helping identify N+1 query patterns and performance bottlenecks.
"""
import time
import logging
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class QueryStats:
    """Statistics for a single query."""
    query: str
    count: int = 0
    total_time: float = 0.0
    min_time: float = float('inf')
    max_time: float = 0.0
    avg_time: float = 0.0
    locations: List[str] = field(default_factory=list)

    def update(self, duration: float, location: str):
        """Update stats with new query execution."""
        self.count += 1
        self.total_time += duration
        self.min_time = min(self.min_time, duration)
        self.max_time = max(self.max_time, duration)
        self.avg_time = self.total_time / self.count
        if location not in self.locations:
            self.locations.append(location)


class QueryProfiler:
    """
    Profile database queries to detect N+1 patterns and performance issues.

    Usage:
        profiler = QueryProfiler()

        async with profiler.profile("get_user_posts"):
            # Your database queries here
            pass

        # Get profiling report
        report = profiler.get_report()
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.queries: Dict[str, QueryStats] = {}
        self.current_context: Optional[str] = None
        self.n1_patterns: List[Dict[str, Any]] = []

    def reset(self):
        """Reset all profiling data."""
        self.queries.clear()
        self.n1_patterns.clear()
        self.current_context = None

    @asynccontextmanager
    async def profile(self, context: str):
        """
        Context manager to profile queries within a specific context.

        Args:
            context: Name of the operation being profiled
        """
        if not self.enabled:
            yield
            return

        old_context = self.current_context
        self.current_context = context
        start_time = time.time()
        query_count_before = sum(stats.count for stats in self.queries.values())

        try:
            yield self
        finally:
            duration = time.time() - start_time
            query_count_after = sum(stats.count for stats in self.queries.values())
            queries_executed = query_count_after - query_count_before

            # Detect potential N+1 if many queries in short time
            if queries_executed > 10 and duration < 1.0:
                self.n1_patterns.append({
                    'context': context,
                    'query_count': queries_executed,
                    'duration': duration,
                    'queries_per_second': queries_executed / duration if duration > 0 else 0
                })
                logger.warning(
                    f"Potential N+1 pattern detected in '{context}': "
                    f"{queries_executed} queries in {duration:.3f}s"
                )

            self.current_context = old_context

    def record_query(self, query: str, duration: float, location: str = "unknown"):
        """
        Record a query execution.

        Args:
            query: SQL query string (normalized)
            duration: Query execution time in seconds
            location: Source location (file:line)
        """
        if not self.enabled:
            return

        # Normalize query (remove whitespace, params)
        normalized = ' '.join(query.split())

        if normalized not in self.queries:
            self.queries[normalized] = QueryStats(query=normalized)

        context_location = f"{self.current_context or 'global'}:{location}"
        self.queries[normalized].update(duration, context_location)

    def get_report(self, top_n: int = 20) -> Dict[str, Any]:
        """
        Generate profiling report.

        Args:
            top_n: Number of top queries to include

        Returns:
            Dictionary containing profiling statistics
        """
        total_queries = sum(stats.count for stats in self.queries.values())
        total_time = sum(stats.total_time for stats in self.queries.values())

        # Sort queries by total time
        sorted_queries = sorted(
            self.queries.values(),
            key=lambda x: x.total_time,
            reverse=True
        )

        # Find duplicate queries (potential N+1)
        duplicates = [
            {
                'query': stats.query[:200],  # Truncate for readability
                'count': stats.count,
                'total_time': round(stats.total_time, 3),
                'avg_time': round(stats.avg_time, 4),
                'locations': stats.locations[:5]  # First 5 locations
            }
            for stats in sorted_queries
            if stats.count > 5  # Executed more than 5 times
        ]

        return {
            'summary': {
                'total_queries': total_queries,
                'unique_queries': len(self.queries),
                'total_time': round(total_time, 3),
                'avg_query_time': round(total_time / total_queries, 4) if total_queries > 0 else 0
            },
            'slowest_queries': [
                {
                    'query': stats.query[:200],
                    'count': stats.count,
                    'total_time': round(stats.total_time, 3),
                    'max_time': round(stats.max_time, 4),
                    'avg_time': round(stats.avg_time, 4)
                }
                for stats in sorted_queries[:top_n]
            ],
            'most_frequent': [
                {
                    'query': stats.query[:200],
                    'count': stats.count,
                    'total_time': round(stats.total_time, 3),
                    'avg_time': round(stats.avg_time, 4)
                }
                for stats in sorted(self.queries.values(), key=lambda x: x.count, reverse=True)[:top_n]
            ],
            'potential_n1_patterns': duplicates[:10],
            'n1_contexts': self.n1_patterns
        }

    def print_report(self):
        """Print formatted profiling report to logger."""
        report = self.get_report()

        logger.info("=" * 80)
        logger.info("QUERY PROFILING REPORT")
        logger.info("=" * 80)
        logger.info(f"Total Queries: {report['summary']['total_queries']}")
        logger.info(f"Unique Queries: {report['summary']['unique_queries']}")
        logger.info(f"Total Time: {report['summary']['total_time']}s")
        logger.info(f"Avg Query Time: {report['summary']['avg_query_time']}s")

        if report['n1_contexts']:
            logger.warning("")
            logger.warning("POTENTIAL N+1 PATTERNS DETECTED:")
            for pattern in report['n1_contexts']:
                logger.warning(
                    f"  - {pattern['context']}: {pattern['query_count']} queries "
                    f"in {pattern['duration']:.3f}s ({pattern['queries_per_second']:.0f} q/s)"
                )

        if report['potential_n1_patterns']:
            logger.warning("")
            logger.warning("FREQUENTLY EXECUTED QUERIES (Potential N+1):")
            for i, query_info in enumerate(report['potential_n1_patterns'][:5], 1):
                logger.warning(
                    f"  {i}. Executed {query_info['count']} times "
                    f"({query_info['total_time']}s total, {query_info['avg_time']}s avg)"
                )
                logger.warning(f"     Query: {query_info['query']}")

        logger.info("")
        logger.info("TOP 10 SLOWEST QUERIES:")
        for i, query_info in enumerate(report['slowest_queries'][:10], 1):
            logger.info(
                f"  {i}. {query_info['total_time']}s total "
                f"({query_info['count']} executions, {query_info['avg_time']}s avg)"
            )
            logger.info(f"     {query_info['query']}")

        logger.info("=" * 80)


# Global profiler instance
_global_profiler: Optional[QueryProfiler] = None


def get_profiler() -> QueryProfiler:
    """Get or create global profiler instance."""
    global _global_profiler
    if _global_profiler is None:
        _global_profiler = QueryProfiler(enabled=True)
    return _global_profiler


def enable_profiling():
    """Enable query profiling globally."""
    get_profiler().enabled = True


def disable_profiling():
    """Disable query profiling globally."""
    get_profiler().enabled = False


@asynccontextmanager
async def profile_queries(context: str):
    """
    Convenience context manager for profiling queries.

    Usage:
        async with profile_queries("get_user_data"):
            # Your database queries
            user = await get_user(user_id)
            posts = await get_user_posts(user_id)  # Potential N+1!
    """
    profiler = get_profiler()
    async with profiler.profile(context):
        yield profiler
