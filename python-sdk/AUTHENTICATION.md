# StocksBlitz SDK Authentication Guide

## Overview

The StocksBlitz Python SDK supports **dual authentication** to accommodate different use cases:

1. **JWT Authentication** - For user-facing applications (interactive apps, notebooks, scripts)
2. **API Key Authentication** - For server-to-server communication (bots, background services)

---

## Authentication Methods

### Method 1: JWT Authentication (Recommended for Users)

JWT authentication is ideal for:
- Interactive Python scripts
- Jupyter notebooks
- User-facing applications
- Development and testing

**Advantages:**
- ✅ Automatic token refresh (transparent to developer)
- ✅ Short-lived access tokens (15 minutes)
- ✅ Long-lived refresh tokens (30 days with `persist_session=True`)
- ✅ User-based permissions and roles
- ✅ Session management and revocation

**Quick Start:**

```python
from stocksblitz import TradingClient

# One-line authentication
client = TradingClient.from_credentials(
    api_url="http://localhost:8081",
    user_service_url="http://localhost:8001",
    username="your_email@example.com",
    password="your_password"
)

# Client is ready to use - tokens auto-refresh!
inst = client.Instrument("NIFTY50")
print(inst['5m'].close)
```

**Alternative (two-step):**

```python
client = TradingClient(
    api_url="http://localhost:8081",
    user_service_url="http://localhost:8001"
)

# Login manually
client.login("your_email@example.com", "your_password")

# Use client
inst = client.Instrument("NIFTY50")

# Logout when done
client.logout()
```

---

### Method 2: API Key Authentication (Recommended for Servers)

API key authentication is ideal for:
- Automated trading bots
- Background services
- Server-to-server communication
- CI/CD pipelines
- Scheduled tasks

**Advantages:**
- ✅ Long-lived credentials (no expiration unless revoked)
- ✅ No login/logout flow
- ✅ Simple to use in automation
- ✅ Per-key permissions and rate limits
- ✅ IP whitelisting support

**Quick Start:**

```python
from stocksblitz import TradingClient

# Simple initialization with API key
client = TradingClient(
    api_url="http://localhost:8081",
    api_key="sb_30d4d5ea_bbb52c64cc4eb2536fdd7b44861c93e4b30b50c6"
)

# Client is ready to use
inst = client.Instrument("NIFTY50")
print(inst['5m'].close)
```

**Creating API Keys:**

API keys must be created via the backend API (requires admin access):

```bash
# Create API key
curl -X POST http://localhost:8081/api/keys/create \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ADMIN_JWT" \
  -d '{
    "user_id": "user:123",
    "name": "Trading Bot Production",
    "permissions": {
      "can_read": true,
      "can_trade": true,
      "can_cancel": true
    },
    "rate_limit_orders_per_sec": 10,
    "rate_limit_requests_per_min": 200,
    "ip_whitelist": ["203.0.113.1"],
    "allowed_accounts": ["primary"]
  }'

# Returns:
# {
#   "api_key": "sb_30d4d5ea_bbb52c64...",  # Save this! Only shown once
#   "key_id": "uuid",
#   "key_prefix": "sb_30d4d5ea"
# }
```

---

## Architecture Overview

### JWT Authentication Flow

```
┌─────────────────┐
│  Python SDK     │
│  TradingClient  │
└────────┬────────┘
         │
         │ 1. login(username, password)
         ▼
┌─────────────────┐
│  User Service   │ ← Validates credentials
│  (port 8001)    │ ← Issues JWT tokens
└────────┬────────┘
         │
         │ 2. Returns:
         │    - access_token (15 min)
         │    - refresh_token (30 days)
         ▼
┌─────────────────┐
│  Python SDK     │ ← Stores tokens
│  APIClient      │ ← Auto-refreshes before expiry
└────────┬────────┘
         │
         │ 3. API requests with JWT
         ▼
┌─────────────────┐
│  Backend API    │ ← Validates JWT via JWKS
│  (port 8081)    │ ← Checks permissions
└─────────────────┘
```

### API Key Authentication Flow

```
┌─────────────────┐
│  Python SDK     │
│  TradingClient  │
└────────┬────────┘
         │
         │ API requests with API key
         ▼
┌─────────────────┐
│  Backend API    │ ← Validates API key hash
│  (port 8081)    │ ← Checks permissions, rate limits, IP
└─────────────────┘
```

---

## Security Best Practices

### For JWT Authentication:

1. **Never hardcode credentials** in source code
   ```python
   # ❌ BAD
   client = TradingClient.from_credentials(
       username="user@example.com",
       password="my_password"  # Hardcoded!
   )

   # ✅ GOOD
   import os
   client = TradingClient.from_credentials(
       username=os.getenv("TRADING_USERNAME"),
       password=os.getenv("TRADING_PASSWORD")
   )
   ```

2. **Use environment variables** or secure credential stores
3. **Enable MFA** on user accounts when available
4. **Use `persist_session=True`** for long-running scripts to get refresh tokens
5. **Call `logout()`** when done to revoke session

### For API Key Authentication:

1. **Store API keys securely**
   - Use environment variables: `os.getenv("STOCKSBLITZ_API_KEY")`
   - Use secrets managers: AWS Secrets Manager, HashiCorp Vault
   - Never commit to version control

2. **Use different keys for different environments**
   - Development: `sb_dev_*`
   - Staging: `sb_staging_*`
   - Production: `sb_prod_*`

3. **Enable IP whitelisting** when possible
4. **Set appropriate rate limits** per key
5. **Rotate keys periodically** (e.g., every 90 days)
6. **Revoke unused keys** immediately

---

## Error Handling

```python
from stocksblitz import TradingClient, AuthenticationError, APIError

try:
    client = TradingClient.from_credentials(
        api_url="http://localhost:8081",
        user_service_url="http://localhost:8001",
        username="user@example.com",
        password="wrong_password"
    )
except AuthenticationError as e:
    print(f"Login failed: {e}")
    # Handle: retry, notify user, etc.

except APIError as e:
    print(f"API error: {e}")
    if e.status_code == 429:
        print("Rate limit exceeded")
    # Handle other API errors

except Exception as e:
    print(f"Unexpected error: {e}")
```

---

## Token Refresh (JWT)

Token refresh is **automatic and transparent**. The SDK handles this internally:

```python
client = TradingClient.from_credentials(
    username="user@example.com",
    password="password",
    persist_session=True  # Get refresh token
)

# Access token expires in 15 minutes
# But you can use the client for 30 days!
# The SDK auto-refreshes tokens before expiry

for i in range(1000):
    time.sleep(60)  # Sleep 1 minute
    inst = client.Instrument("NIFTY50")
    print(f"Iteration {i}: {inst['5m'].close}")
    # SDK automatically refreshes token if needed
```

**How it works:**
1. Access token expires in 15 minutes
2. SDK checks expiry before each request
3. If expiring within 60 seconds, SDK calls `/v1/auth/refresh`
4. New access token obtained using refresh token
5. Request proceeds with new token

**When refresh fails:**
- Refresh token expired (> 30 days)
- Refresh token revoked
- User account disabled

→ SDK raises `AuthenticationError` → Re-login required

---

## Comparison: JWT vs API Key

| Feature | JWT Auth | API Key Auth |
|---------|----------|--------------|
| **Use Case** | User-facing apps | Server-to-server |
| **Setup** | Login with username/password | Obtain API key from admin |
| **Token Lifetime** | 15 min (access), 30 days (refresh) | Indefinite (until revoked) |
| **Auto-refresh** | ✅ Yes | N/A |
| **Session Management** | ✅ Yes | ❌ No |
| **User Identity** | ✅ Yes | ⚠️ Service identity |
| **IP Whitelisting** | ❌ No | ✅ Yes |
| **Rate Limiting** | Per user | Per API key |
| **Revocation** | Logout or admin revoke | Admin revoke |
| **Audit Trail** | Per user session | Per API key |

---

## Migration Guide

### From Old SDK (API Key Only)

**Before:**
```python
client = TradingClient(
    api_url="http://localhost:8009",
    api_key="sb_xxx_yyy"
)
```

**After (JWT for users):**
```python
client = TradingClient.from_credentials(
    api_url="http://localhost:8081",
    user_service_url="http://localhost:8001",
    username="user@example.com",
    password="password"
)
```

**After (API key for servers - unchanged):**
```python
client = TradingClient(
    api_url="http://localhost:8081",
    api_key="sb_xxx_yyy"
)
```

---

## Examples

### Example 1: Jupyter Notebook (JWT)

```python
# In first cell
from stocksblitz import TradingClient

client = TradingClient.from_credentials(
    api_url="http://localhost:8081",
    user_service_url="http://localhost:8001",
    username="trader@example.com",
    password="MySecurePassword123"
)

# In subsequent cells
inst = client.Instrument("NIFTY50")
print(f"NIFTY50 Price: {inst['5m'].close}")

# Tokens auto-refresh throughout notebook session
```

### Example 2: Trading Bot (API Key)

```python
import os
from stocksblitz import TradingClient

# Load API key from environment
API_KEY = os.getenv("STOCKSBLITZ_API_KEY")

client = TradingClient(
    api_url="http://localhost:8081",
    api_key=API_KEY
)

# Run bot logic
while True:
    inst = client.Instrument("NIFTY50")
    if inst['5m'].rsi[14] > 70:
        client.Account().sell(inst, quantity=50)
    time.sleep(60)
```

### Example 3: Automated Script with Error Handling

```python
import os
import sys
from stocksblitz import TradingClient, AuthenticationError

def main():
    try:
        client = TradingClient.from_credentials(
            api_url=os.getenv("API_URL"),
            user_service_url=os.getenv("USER_SERVICE_URL"),
            username=os.getenv("TRADING_USERNAME"),
            password=os.getenv("TRADING_PASSWORD"),
            persist_session=True
        )

        # Run trading logic
        execute_strategy(client)

    except AuthenticationError as e:
        print(f"Authentication failed: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if 'client' in locals():
            client.logout()

if __name__ == "__main__":
    main()
```

---

## FAQ

**Q: Which authentication method should I use?**
A: Use JWT for interactive/user applications. Use API keys for automated services.

**Q: Can I use both methods in the same application?**
A: Yes, but not on the same `TradingClient` instance. Create separate clients.

**Q: How do I get an API key?**
A: Contact your administrator or use the backend API `/api/keys/create` endpoint.

**Q: What happens when my JWT expires?**
A: The SDK automatically refreshes it using the refresh token. No action needed.

**Q: Can I use JWT without `persist_session`?**
A: Yes, but you'll need to re-login after 15 minutes when the access token expires.

**Q: How do I revoke an API key?**
A: Use the backend API: `DELETE /api/keys/{key_id}` or contact your administrator.

**Q: Is my password stored by the SDK?**
A: No. The SDK only stores JWT tokens after login. Passwords are never stored.

---

## Support

For issues or questions:
- GitHub Issues: https://github.com/yourusername/stocksblitz-sdk/issues
- Documentation: https://docs.stocksblitz.com
- Email: support@stocksblitz.com
