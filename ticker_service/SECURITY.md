# Security Guidelines

## Secrets Management

### Development Environment

1. **Copy the example environment file:**
   ```bash
   cp .env.example .env
   ```

2. **Generate strong API key:**
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

3. **Generate encryption key for account storage:**
   ```bash
   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

4. **Fill in your credentials in `.env`** - never commit this file!

### Production Environment

**NEVER use `.env` files in production!** Use a proper secrets management solution:

#### AWS
```bash
# Store secrets in AWS Secrets Manager
aws secretsmanager create-secret \
    --name ticker-service/api-key \
    --secret-string "your-api-key"

# Or use AWS Systems Manager Parameter Store
aws ssm put-parameter \
    --name /ticker-service/api-key \
    --value "your-api-key" \
    --type SecureString
```

#### Kubernetes
```yaml
# Use Sealed Secrets or External Secrets Operator
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: ticker-service-secrets
spec:
  secretStoreRef:
    name: aws-secrets-manager
  target:
    name: ticker-service-env
  data:
    - secretKey: API_KEY
      remoteRef:
        key: ticker-service/api-key
```

#### Docker Compose (Production)
```yaml
services:
  ticker-service:
    environment:
      API_KEY: ${API_KEY}  # Read from host environment
      INSTRUMENT_DB_PASSWORD: ${DB_PASSWORD}
    # Or use Docker secrets
    secrets:
      - api_key
      - db_password

secrets:
  api_key:
    external: true
  db_password:
    external: true
```

## Authentication

### API Key Authentication

**Enabled by default in all environments.**

All protected endpoints require the `X-API-Key` header:

```bash
curl -H "X-API-Key: your-api-key" \
  http://localhost:8080/advanced/batch-orders
```

### WebSocket Authentication

WebSocket connections require authentication via the first message:

```javascript
const ws = new WebSocket('ws://localhost:8080/advanced/ws/orders/primary');

ws.onopen = () => {
  // MUST send auth as first message
  ws.send(JSON.stringify({
    type: "auth",
    api_key: "your-api-key"
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === "authenticated") {
    console.log("Connected!");
  }
};
```

### Disabling Authentication (Development Only)

To disable authentication in development:

```bash
# .env
API_KEY_ENABLED=false
ENVIRONMENT=development
```

**WARNING**: Setting `ENVIRONMENT=production` will enforce authentication regardless of `API_KEY_ENABLED`.

## Rate Limiting

All endpoints have rate limits to prevent abuse:

| Endpoint | Limit |
|----------|-------|
| `/health` | 60/minute |
| `/subscriptions` (GET) | 100/minute |
| `/subscriptions` (POST/DELETE) | 30/minute |
| `/admin/instrument-refresh` | 5/hour |
| `/advanced/batch-orders` | 10/minute |
| `/advanced/webhooks` (POST) | 20/minute |
| `/advanced/backpressure/reset-circuit-breaker` | 5/minute |

Limits are per IP address. Rate limit exceeded returns `429 Too Many Requests`.

## Security Checklist

### Before Production Deployment

- [ ] Generate strong API key (32+ bytes, random)
- [ ] Store secrets in proper secrets manager (not .env files)
- [ ] Set `ENVIRONMENT=production`
- [ ] Verify `API_KEY_ENABLED=true`
- [ ] Change all default passwords (database, Redis, etc.)
- [ ] Enable HTTPS/TLS on all endpoints
- [ ] Configure firewall rules (only allow necessary ports)
- [ ] Set up log monitoring and alerting
- [ ] Review and restrict database user permissions
- [ ] Enable audit logging for authentication failures
- [ ] Set up intrusion detection (fail2ban, etc.)
- [ ] Configure backup encryption
- [ ] Test disaster recovery procedures

### Regular Maintenance

- [ ] Rotate API keys every 90 days
- [ ] Review access logs for suspicious activity
- [ ] Update dependencies monthly (`pip list --outdated`)
- [ ] Review and update rate limits based on usage
- [ ] Test backup restoration quarterly
- [ ] Audit user access and permissions

## Common Security Issues

### 1. Secrets in Logs

**Risk**: API keys, tokens, or passwords in log files

**Mitigation**:
- Logs use PII sanitization (see `app/main.py:40-54`)
- Redacts emails, phone numbers, API keys/tokens
- Never log request headers or query parameters containing sensitive data

### 2. SQL Injection

**Risk**: User input in database queries

**Mitigation**:
- All database queries use parameterized queries
- Input validation on all endpoints
- See `app/task_persistence.py:169-177` for example

### 3. SSRF (Server-Side Request Forgery)

**Risk**: Webhook URLs pointing to internal services

**Mitigation**:
- Webhook URLs validated against private IP ranges
- Blocks localhost, 127.0.0.1, RFC1918 addresses
- See `app/routes_advanced.py:125-148`

### 4. Unauthorized Access

**Risk**: Endpoints accessible without authentication

**Mitigation**:
- Authentication enabled by default
- All sensitive endpoints require API key
- Production environment enforces authentication

## Incident Response

### Suspected API Key Compromise

1. **Immediate Action**:
   ```bash
   # Generate new API key
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"

   # Update secret in secrets manager
   aws secretsmanager update-secret \
     --secret-id ticker-service/api-key \
     --secret-string "new-api-key"

   # Restart service to pick up new key
   docker-compose restart ticker-service
   ```

2. **Investigation**:
   - Review access logs for unauthorized requests
   - Check for unusual order patterns
   - Audit recent configuration changes

3. **Prevention**:
   - Update documentation with new key rotation schedule
   - Add monitoring alerts for failed authentication attempts

### Suspected Database Breach

1. **Immediate Action**:
   - Rotate database password
   - Review database logs for suspicious queries
   - Check for data exfiltration in audit logs

2. **Assess Impact**:
   - Determine what data was accessed
   - Check for data modification or deletion
   - Verify backup integrity

3. **Notify stakeholders** per company policy

## Contact

For security vulnerabilities, please email: security@yourcompany.com

**Do NOT open public GitHub issues for security vulnerabilities.**
