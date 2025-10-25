# Ticker Service

FastAPI microservice responsible for fetching historical and real-time data from Kite, computing F&O analytics (PCR, Greeks, max pain, moneyness), and publishing them via Redis pub/sub.

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
