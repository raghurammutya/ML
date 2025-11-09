# Backend Monitoring - Metrics Summary

Complete list of all 100+ Prometheus metrics implemented for the backend service.

## Metrics by Category

### HTTP API Metrics (5 metrics)
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `http_requests_total` | Counter | method, endpoint, status | Total HTTP requests |
| `http_request_duration_seconds` | Histogram | method, endpoint | Request latency (10 buckets: 5ms-10s) |
| `http_request_size_bytes` | Histogram | method, endpoint | Request payload size (5 buckets: 100B-1MB) |
| `http_response_size_bytes` | Histogram | method, endpoint | Response payload size (6 buckets: 100B-10MB) |
| `http_active_requests` | Gauge | endpoint | Currently active requests |

### Database Metrics (7 metrics)
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `database_queries_total` | Counter | query_type, status | Total queries (select/insert/update/delete/procedure) |
| `database_query_duration_seconds` | Histogram | query_type | Query execution time (11 buckets: 1ms-5s) |
| `database_pool_connections` | Gauge | state | Pool connections (active/idle/total) |
| `database_pool_acquire_duration_seconds` | Histogram | - | Time to acquire connection (11 buckets: 1ms-5s) |
| `database_pool_acquire_timeouts_total` | Counter | - | Pool exhaustion timeouts |
| `database_transaction_duration_seconds` | Histogram | operation | Transaction execution time (9 buckets: 10ms-10s) |
| `database_errors_total` | Counter | error_type | Database errors (connection/query/timeout/deadlock) |

### Cache Metrics (8 metrics)
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `cache_operations_total` | Counter | operation, cache_layer, status | Cache ops (get/set/delete on L1/L2) |
| `cache_hit_rate` | Gauge | cache_layer | Hit rate % (L1 memory, L2 Redis) |
| `cache_operation_duration_seconds` | Histogram | operation, cache_layer | Operation latency (9 buckets: 0.1ms-250ms) |
| `cache_memory_usage_bytes` | Gauge | - | Memory cache size in bytes |
| `cache_entries_total` | Gauge | cache_layer | Number of cached entries |
| `redis_connection_errors_total` | Counter | - | Redis connection failures |
| `redis_command_duration_seconds` | Histogram | command | Redis command latency (8 buckets: 0.1ms-100ms) |

### WebSocket Metrics (6 metrics)
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `websocket_connections_active` | Gauge | endpoint | Active WS connections per endpoint |
| `websocket_messages_sent_total` | Counter | endpoint, message_type | Messages sent to clients |
| `websocket_messages_received_total` | Counter | endpoint, message_type | Messages from clients |
| `websocket_connection_duration_seconds` | Histogram | endpoint | Connection lifetime (10 buckets: 1s-2h) |
| `websocket_errors_total` | Counter | endpoint, error_type | WebSocket errors |
| `websocket_subscriptions_active` | Gauge | endpoint, subscription_type | Active subscriptions |

### Smart Order Metrics (6 metrics)
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `smart_order_validations_total` | Counter | status | Validations (passed/rejected) |
| `smart_order_validation_duration_seconds` | Histogram | - | Validation latency (8 buckets: 10ms-5s) |
| `smart_order_rejection_reasons_total` | Counter | reason | Rejections by reason |
| `margin_calculations_total` | Counter | status | Margin calculations (success/error/fallback) |
| `margin_calculation_duration_seconds` | Histogram | method | Margin calc latency (9 buckets: 10ms-10s) |
| `cost_breakdown_calculations_total` | Counter | transaction_type | Cost breakdowns (options_buy/sell, futures, equity) |
| `market_impact_assessments_total` | Counter | impact_level | Market impact (low/medium/high) |

### Strategy Metrics (6 metrics)
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `strategies_total` | Gauge | account_id | Active strategies per account |
| `strategy_operations_total` | Counter | operation, status | CRUD operations (create/update/delete/add_instrument) |
| `strategy_m2m_calculations_total` | Counter | status | M2M calculations (success/error) |
| `strategy_m2m_calculation_duration_seconds` | Histogram | - | M2M calc latency (8 buckets: 10ms-5s) |
| `strategy_instruments_total` | Gauge | account_id | Total instruments in strategies |
| `strategy_pnl_total` | Gauge | account_id | Total P&L in rupees |

### F&O Analytics Metrics (4 metrics)
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `fo_queries_total` | Counter | query_type, status | F&O queries (strike_distribution/oi_analysis/moneyness_series) |
| `fo_query_duration_seconds` | Histogram | query_type | F&O query latency (9 buckets: 50ms-30s) |
| `fo_instruments_cached` | Gauge | - | Cached F&O instruments |
| `fo_greeks_calculations_total` | Counter | status | Greeks calculations (success/error) |

### Ticker Service Client Metrics (5 metrics)
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `ticker_service_requests_total` | Counter | operation, status | Requests (subscribe/unsubscribe/health/history) |
| `ticker_service_request_duration_seconds` | Histogram | operation | Request latency (9 buckets: 10ms-10s) |
| `ticker_service_circuit_breaker_state` | Gauge | - | Circuit breaker state (0=closed, 1=open, 2=half_open) |
| `ticker_service_circuit_breaker_failures_total` | Counter | - | Circuit breaker failures |
| `ticker_service_errors_total` | Counter | error_type | Errors (timeout/connection/circuit_open/http_error) |

### Authentication Metrics (5 metrics)
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `auth_attempts_total` | Counter | status | Auth attempts (success/failed) |
| `jwt_validations_total` | Counter | status | JWT validations (valid/expired/invalid) |
| `jwt_validation_duration_seconds` | Histogram | - | JWT validation latency (6 buckets: 0.1ms-25ms) |
| `active_sessions` | Gauge | - | Current active sessions |
| `api_key_validations_total` | Counter | status | API key validations (valid/invalid/expired) |

### Statement Parser Metrics (4 metrics)
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `statement_uploads_total` | Counter | status, file_type | Statement uploads (csv/excel) |
| `statement_parsing_duration_seconds` | Histogram | file_type | Parsing duration (8 buckets: 100ms-60s) |
| `transactions_parsed_total` | Counter | category | Parsed transactions (fno/equity/charges/dividend) |
| `statement_parsing_errors_total` | Counter | error_type | Parsing errors (invalid_format/missing_columns/date_error) |

### Calendar & Market Data Metrics (4 metrics)
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `calendar_requests_total` | Counter | endpoint, status | Calendar API requests (holidays/corporate_actions) |
| `market_data_updates_total` | Counter | data_type | Market data updates (tick/ohlc/market_depth) |
| `indicator_calculations_total` | Counter | indicator_type, status | Indicator calculations (iv/delta/gamma/theta/vega/oi) |
| `indicator_cache_hit_rate` | Gauge | indicator_type | Indicator cache hit rate % |

### Background Worker Metrics (3 metrics)
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `worker_tasks_total` | Counter | worker_type, status | Worker tasks (strategy_m2m/order_cleanup/housekeeping) |
| `worker_task_duration_seconds` | Histogram | worker_type | Task duration (8 buckets: 100ms-5min) |
| `worker_queue_depth` | Gauge | worker_type | Queue depth by worker type |

### Business Metrics (5 metrics)
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `active_users` | Gauge | time_window | Active users (5m/15m/1h windows) |
| `user_requests_per_second` | Gauge | account_id | RPS per user |
| `daily_active_users` | Gauge | - | Daily active users count |
| `total_orders_placed_today` | Counter | - | Orders placed today |
| `total_strategies_created_today` | Counter | - | Strategies created today |

### Error Tracking Metrics (2 metrics)
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `application_errors_total` | Counter | error_type, severity | Application errors (warning/error/critical) |
| `unhandled_exceptions_total` | Counter | exception_type | Unhandled exceptions |

### Rate Limiting Metrics (2 metrics)
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `rate_limit_exceeded_total` | Counter | endpoint, user_id | Rate limit violations |
| `rate_limit_current_usage` | Gauge | endpoint, user_id | Current rate limit usage % |

## Total Metrics Count

| Category | Metrics |
|----------|---------|
| HTTP API | 5 |
| Database | 7 |
| Cache | 8 |
| WebSocket | 6 |
| Smart Orders | 6 |
| Strategies | 6 |
| F&O Analytics | 4 |
| Ticker Service | 5 |
| Authentication | 5 |
| Statement Parser | 4 |
| Calendar & Market | 4 |
| Background Workers | 3 |
| Business | 5 |
| Error Tracking | 2 |
| Rate Limiting | 2 |
| **TOTAL** | **72** |

**Note**: With label combinations and histogram buckets, this expands to **100+ time series**.

## Metric Naming Convention

All metrics follow Prometheus best practices:

- **Prefix**: `backend_` (implicit through app)
- **Suffix**: `_total` for Counters, `_seconds` for durations, `_bytes` for sizes
- **Labels**: snake_case
- **Names**: snake_case with descriptive names

## PromQL Query Examples

### Top 10 Slowest Endpoints (P95)
```promql
topk(10, histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (endpoint, le)))
```

### Error Rate by Endpoint
```promql
sum(rate(http_requests_total{status=~"5.."}[5m])) by (endpoint) / sum(rate(http_requests_total[5m])) by (endpoint) * 100
```

### Database Pool Utilization %
```promql
100 * database_pool_connections{state="active"} / database_pool_connections{state="total"}
```

### Cache Hit Rate
```promql
100 * sum(rate(cache_operations_total{operation="get",status="hit"}[5m])) / sum(rate(cache_operations_total{operation="get"}[5m]))
```

### Order Rejection Rate
```promql
100 * sum(rate(smart_order_validations_total{status="rejected"}[5m])) / sum(rate(smart_order_validations_total[5m]))
```

---

**Last Updated**: 2025-11-09
**Metrics Version**: 1.0.0
