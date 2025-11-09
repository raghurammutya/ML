#!/bin/bash
#
# Load Testing Quick Start Script
#
# Usage:
#   ./run_load_tests.sh [scenario] [host]
#
# Scenarios:
#   baseline    - Normal load (50 users, 5min)
#   spike       - Sudden spike (500 users, 2min)
#   sustained   - Long-running (200 users, 30min)
#   db-heavy    - Database stress (100 users, 10min)
#   read-heavy  - Read operations (500 users, 10min)
#

set -e

SCENARIO="${1:-baseline}"
HOST="${2:-http://localhost:8000}"
REPORT_DIR="reports"

# Create reports directory
mkdir -p "$REPORT_DIR"

# Check if locust is installed
if ! command -v locust &> /dev/null; then
    echo "❌ Locust not found. Installing..."
    pip install locust==2.20.0
fi

echo "🚀 Starting load test: $SCENARIO"
echo "   Target host: $HOST"
echo "   Report dir: $REPORT_DIR"
echo ""

case "$SCENARIO" in
    baseline)
        echo "📊 Running baseline performance test (50 users, 5 minutes)"
        locust -f tests/load/locustfile.py \
            --host="$HOST" \
            MixedWorkloadUser \
            --users 50 \
            --spawn-rate 5 \
            --run-time 5m \
            --headless \
            --html "$REPORT_DIR/baseline_test.html" \
            --csv "$REPORT_DIR/baseline_test"
        ;;

    spike)
        echo "⚡ Running spike test (500 users, 2 minutes)"
        locust -f tests/load/locustfile.py \
            --host="$HOST" \
            MixedWorkloadUser \
            --users 500 \
            --spawn-rate 100 \
            --run-time 2m \
            --headless \
            --html "$REPORT_DIR/spike_test.html" \
            --csv "$REPORT_DIR/spike_test"
        ;;

    sustained)
        echo "⏱️  Running sustained load test (200 users, 30 minutes)"
        locust -f tests/load/locustfile.py \
            --host="$HOST" \
            MixedWorkloadUser \
            --users 200 \
            --spawn-rate 10 \
            --run-time 30m \
            --headless \
            --html "$REPORT_DIR/sustained_test.html" \
            --csv "$REPORT_DIR/sustained_test"
        ;;

    db-heavy)
        echo "💾 Running database-heavy test (100 users, 10 minutes)"
        locust -f tests/load/locustfile.py \
            --host="$HOST" \
            APIUser \
            --users 100 \
            --spawn-rate 20 \
            --run-time 10m \
            --headless \
            --html "$REPORT_DIR/db_heavy_test.html" \
            --csv "$REPORT_DIR/db_heavy_test"
        ;;

    read-heavy)
        echo "📖 Running read-heavy test (500 users, 10 minutes)"
        locust -f tests/load/locustfile.py \
            --host="$HOST" \
            ReadOnlyUser \
            --users 500 \
            --spawn-rate 50 \
            --run-time 10m \
            --headless \
            --html "$REPORT_DIR/read_heavy_test.html" \
            --csv "$REPORT_DIR/read_heavy_test"
        ;;

    interactive)
        echo "🌐 Starting interactive web UI mode"
        echo "   Open http://localhost:8089 in your browser"
        locust -f tests/load/locustfile.py --host="$HOST"
        ;;

    *)
        echo "❌ Unknown scenario: $SCENARIO"
        echo ""
        echo "Available scenarios:"
        echo "  baseline    - Normal load (50 users, 5min)"
        echo "  spike       - Sudden spike (500 users, 2min)"
        echo "  sustained   - Long-running (200 users, 30min)"
        echo "  db-heavy    - Database stress (100 users, 10min)"
        echo "  read-heavy  - Read operations (500 users, 10min)"
        echo "  interactive - Web UI mode"
        exit 1
        ;;
esac

echo ""
echo "✅ Load test complete!"
echo "   Report: $REPORT_DIR/${SCENARIO}_test.html"
echo ""

# Open report if running on macOS or Linux with xdg-open
if [[ "$OSTYPE" == "darwin"* ]]; then
    open "$REPORT_DIR/${SCENARIO}_test.html"
elif command -v xdg-open &> /dev/null; then
    xdg-open "$REPORT_DIR/${SCENARIO}_test.html"
fi
