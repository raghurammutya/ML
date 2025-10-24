#!/bin/bash

# Test TradingView UDF endpoints

BASE_URL="http://5.223.52.98:8888"

echo "Testing TradingView UDF endpoints..."
echo "===================================="

# Test config endpoint
echo -e "\n1. Testing /config endpoint:"
curl -s "$BASE_URL/config" | python3 -m json.tool

# Test symbol info
echo -e "\n2. Testing /symbols endpoint:"
curl -s "$BASE_URL/symbols?symbol=NIFTY50" | python3 -m json.tool

# Test search
echo -e "\n3. Testing /search endpoint:"
curl -s "$BASE_URL/search?query=NIFTY&limit=10" | python3 -m json.tool

# Test history (last 24 hours, 5-minute bars)
echo -e "\n4. Testing /history endpoint:"
END_TIME=$(date +%s)
START_TIME=$((END_TIME - 86400))  # 24 hours ago
curl -s "$BASE_URL/history?symbol=NIFTY50&from=$START_TIME&to=$END_TIME&resolution=5" | python3 -m json.tool | head -20

# Test marks
echo -e "\n5. Testing /marks endpoint:"
curl -s "$BASE_URL/marks?symbol=NIFTY50&from=$START_TIME&to=$END_TIME&resolution=5" | python3 -m json.tool | head -20

# Test timescale marks
echo -e "\n6. Testing /timescale_marks endpoint:"
curl -s "$BASE_URL/timescale_marks?symbol=NIFTY50&from=$START_TIME&to=$END_TIME&resolution=5" | python3 -m json.tool | head -20

# Test server time
echo -e "\n7. Testing /time endpoint:"
curl -s "$BASE_URL/time"
echo

# Test health endpoint
echo -e "\n8. Testing /health endpoint:"
curl -s "$BASE_URL/health" | python3 -m json.tool

# Test cache stats
echo -e "\n9. Testing /cache/stats endpoint:"
curl -s "$BASE_URL/cache/stats" | python3 -m json.tool

# Test label distribution
echo -e "\n10. Testing /api/label-distribution endpoint:"
curl -s "$BASE_URL/api/label-distribution?timeframe=5min&days=7" | python3 -m json.tool

echo -e "\n===================================="
echo "All tests completed!"