#!/bin/bash
#
# Load Test Runner
# Runs comprehensive load tests and generates performance report
#

set -e

echo "=========================================="
echo "Ticker Service Load Tests"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo -e "${RED}Error: Virtual environment not found${NC}"
    echo "Please run: python -m venv .venv && .venv/bin/pip install -e ."
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

echo "Running load tests..."
echo ""

# Run load tests with detailed output
# Excluding slow tests by default (use --run-slow to include)
if [ "$1" == "--run-slow" ]; then
    echo -e "${YELLOW}Running ALL load tests (including slow tests)${NC}"
    pytest tests/load/ -v -m load --tb=short -s
else
    echo -e "${YELLOW}Running fast load tests (use --run-slow for all)${NC}"
    pytest tests/load/ -v -m "load and not slow" --tb=short -s
fi

EXIT_CODE=$?

echo ""
echo "=========================================="
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}Load tests PASSED${NC}"
else
    echo -e "${RED}Load tests FAILED${NC}"
fi
echo "=========================================="

exit $EXIT_CODE
