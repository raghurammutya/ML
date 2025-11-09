# Ticker Service Monitoring

Comprehensive monitoring stack for tick processing performance and health.

## Overview

The monitoring stack provides:
- **Grafana Dashboard**: Real-time visualization of 20+ metrics
- **Prometheus Alerts**: 15+ alerting rules for critical conditions
- **Performance Insights**: Latency, throughput, errors, and business metrics

## Quick Start

### 1. Deploy Monitoring Stack

```bash
# Set Grafana credentials (optional - for automated deployment)
export GRAFANA_URL=http://localhost:3000
export GRAFANA_API_KEY=your_api_key_here

# Deploy dashboard and alerts
./monitoring/deploy.sh
```

### 2. Manual Import (Alternative)

If automated deployment fails:

**Grafana Dashboard:**
1. Open Grafana UI (http://localhost:3000)
2. Go to Dashboards → Import
3. Upload `grafana/tick-processing-dashboard.json`
4. Select Prometheus data source
5. Click Import

**Prometheus Alerts:**
1. Copy `alerts/tick-processing-alerts.yml` to Prometheus rules directory
2. Reload Prometheus: `curl -X POST http://localhost:9090/-/reload`
3. Verify alerts loaded: http://localhost:9090/alerts

### 3. Verify Deployment

```bash
# Check Grafana dashboard
curl -s http://localhost:3000/api/dashboards/db/tick-processing-performance-health

# Check Prometheus alerts
curl -s http://localhost:9090/api/v1/rules | jq '.data.groups[] | select(.name=="tick_processing")'
```

## Dashboard Panels

### Row 1: Overview (6 panels)

1. **Tick Throughput** - Successful vs failed ticks/sec
2. **Active Accounts** - Number of connected trading accounts
3. **Error Rate** - Errors per second with sparkline
4. **System Health** - UP/DOWN status indicator
5. **Underlying Price** - Current NIFTY price
6. (Additional space for custom metrics)

### Row 2: Latency (3 panels)

7. **Tick Processing Latency** - P50, P95, P99 percentiles
   - Alert triggers if P99 > 100ms for 5 minutes
8. **Batch Flush Latency** - P95 batch flush times
9. **Greeks Calculation Latency** - P95, P99 calculation times

### Row 3: Batching (4 panels)

10. **Batch Size Distribution** - P50, P95 batch sizes
11. **Batches Flushed/sec** - Batch throughput rate
12. **Batch Fill Rate** - Percentage of max batch size utilized
13. **Pending Batch Size** - Current queued ticks

### Row 4: Errors (4 panels)

14. **Validation Errors** - Errors by validation type
15. **Processing Errors** - Errors by error type
16. **Error Rate by Type** - Pie chart of error distribution
17. **Total Errors** - Total errors in last hour

### Row 5: Business Metrics (4 panels)

18. **Underlying Ticks** - Processed underlying ticks/sec
19. **Option Ticks** - Processed option ticks/sec
20. **Greeks Calculations** - Successful vs failed calculations
21. **Market Depth Updates** - Depth update rate

## Alerting Rules

### Critical Alerts (Immediate Action Required)

| Alert | Condition | Duration | Action |
|-------|-----------|----------|--------|
| `CriticalTickProcessingLatency` | P99 > 500ms | 2min | Check logs, restart service if needed |
| `HighTickProcessingErrorRate` | Errors > 10/sec | 2min | Investigate error logs |
| `NoTicksProcessed` | No ticks for 5min | 5min | Check WebSocket connections |
| `NoActiveAccounts` | 0 active accounts | 5min | Check account health |
| `TickProcessorDown` | Service down | 1min | Restart service immediately |

### Warning Alerts (Investigation Needed)

| Alert | Condition | Duration | Action |
|-------|-----------|----------|--------|
| `HighTickProcessingLatency` | P99 > 100ms | 5min | Monitor, investigate if persists |
| `LowTickThroughput` | < 100 ticks/sec | 5min | Check upstream data flow |
| `TickValidationErrorsIncreasing` | > 50 errors/sec | 5min | Check data quality from upstream |
| `HighBatchFlushLatency` | P95 > 500ms | 5min | Check Redis performance |
| `NoGreeksCalculations` | 0 calculations for 10min | 10min | Check option tick flow |

### Info Alerts (Informational)

| Alert | Condition | Duration | Action |
|-------|-----------|----------|--------|
| `LowBatchFillRate` | < 50% fill rate | 15min | Acceptable during low volume |

## Metrics Reference

### Latency Metrics (Histograms)

```promql
# Tick processing latency (P50, P95, P99)
histogram_quantile(0.99, rate(tick_processing_latency_seconds_bucket[5m]))

# Greeks calculation latency
histogram_quantile(0.95, rate(greeks_calculation_latency_seconds_bucket[5m]))

# Batch flush latency
histogram_quantile(0.95, rate(tick_batch_flush_latency_seconds_bucket[5m]))
```

### Throughput Metrics (Counters)

```promql
# Ticks processed per second
rate(ticks_processed_total{status="success"}[1m])

# Ticks published per second
rate(ticks_published_total[1m])

# Greeks calculations per second
rate(greeks_calculations_total{status="success"}[1m])
```

### Error Metrics (Counters)

```promql
# Error rate by type
rate(tick_processing_errors_total[5m])

# Validation errors
rate(tick_validation_errors_total[5m])
```

### State Metrics (Gauges)

```promql
# Active accounts
tick_processor_active_accounts

# Underlying price (NIFTY)
tick_processor_underlying_price{symbol="NIFTY"}

# Pending batch size
tick_batch_pending_size{batch_type="options"}

# Batch fill rate
tick_batch_fill_rate{batch_type="underlying"}
```

## Querying Examples

### Find P99 latency by tick type

```promql
histogram_quantile(0.99,
  sum by (tick_type, le) (
    rate(tick_processing_latency_seconds_bucket[5m])
  )
)
```

### Calculate error rate percentage

```promql
(
  rate(ticks_processed_total{status="error"}[5m])
  /
  rate(ticks_processed_total[5m])
) * 100
```

### Identify slowest Greeks calculations

```promql
topk(10,
  rate(greeks_calculation_latency_seconds_sum[5m])
  /
  rate(greeks_calculations_total[5m])
)
```

## Alert Testing

Test alert firing with load tests:

```bash
# Trigger high latency alert (if applicable)
.venv/bin/pytest tests/load/ -m "load and slow" -s

# Check if alert fired
curl -s http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | select(.labels.alertname=="HighTickProcessingLatency")'
```

## Dashboard Performance

Dashboard metrics:
- **Load time**: < 2 seconds (target)
- **Query performance**: All queries < 1 second
- **Refresh rate**: 10 seconds (configurable)
- **Time range**: Last 1 hour (default)

## Customization

### Adding Custom Panels

1. Edit `grafana/tick-processing-dashboard.json`
2. Add panel configuration in `panels` array
3. Redeploy: `./monitoring/deploy.sh`

### Modifying Alerts

1. Edit `alerts/tick-processing-alerts.yml`
2. Test alert syntax: `promtool check rules alerts/tick-processing-alerts.yml`
3. Redeploy to Prometheus rules directory
4. Reload Prometheus

### Notification Channels

Configure notification channels in Grafana:
1. Go to Alerting → Notification channels
2. Add channel (Slack, PagerDuty, Email, etc.)
3. Link alerts to notification channels

## Troubleshooting

### Dashboard not loading

1. Check Prometheus data source configured
2. Verify metrics are being exported: `curl http://localhost:8000/metrics`
3. Check browser console for errors

### Alerts not firing

1. Verify alerts loaded: `curl http://localhost:9090/api/v1/rules`
2. Check Prometheus logs: `journalctl -u prometheus -f`
3. Validate alert syntax: `promtool check rules alerts/*.yml`

### Missing metrics

1. Ensure ticker service is running
2. Check `/metrics` endpoint is accessible
3. Verify Prometheus scrape configuration
4. Check Prometheus targets: http://localhost:9090/targets

## Production Checklist

- [ ] Grafana dashboard deployed
- [ ] Prometheus alerts loaded
- [ ] Notification channels configured
- [ ] Alert firing tested
- [ ] Dashboard loads in < 2 seconds
- [ ] All panels showing data
- [ ] Team trained on dashboard usage
- [ ] Runbooks linked in alert annotations
- [ ] On-call rotation configured

## References

- [Prometheus Querying Basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Grafana Dashboard Best Practices](https://grafana.com/docs/grafana/latest/best-practices/)
- [Alerting Best Practices](https://prometheus.io/docs/practices/alerting/)

## Support

For issues or questions:
1. Check troubleshooting section above
2. Review Prometheus/Grafana logs
3. Consult team documentation
4. Contact SRE team
