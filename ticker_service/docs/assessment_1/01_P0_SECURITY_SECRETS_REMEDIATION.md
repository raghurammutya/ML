# P0 CRITICAL: Secrets Exposure Remediation

**Role:** Security Engineer + DevOps Engineer
**Priority:** P0 - BLOCKING DEPLOYMENT
**Estimated Effort:** 4-6 hours
**Dependencies:** None
**Must Complete Before:** Any production deployment

---

## Objective

Remove all exposed secrets from version control and implement proper secret management. This addresses **4 CRITICAL security vulnerabilities** that block production deployment.

---

## Context

The following critical secrets are exposed in version control:
1. **Database password** (`stocksblitz123`) in `app/config.py` and `.env`
2. **Kite API access token** in `tokens/kite_token_primary.json`
3. **Base64-encoded credentials** (not proper encryption) in database
4. **Missing CORS configuration** allowing cross-origin attacks

**Risk:** Complete system compromise, unauthorized trading, financial fraud

---

## Tasks

### Task 1: Rotate Database Password (1 hour)

**Current Issue (CVE-TICKER-001):**
```python
# app/config.py:56
instrument_db_password: str = Field(default="stocksblitz123")
```

**Actions:**
```bash
# 1. Generate new secure password
NEW_PASSWORD=$(openssl rand -base64 32)

# 2. Connect to PostgreSQL and rotate
psql -U postgres -h localhost << EOF
ALTER USER stocksuser WITH PASSWORD '$NEW_PASSWORD';
\q
EOF

# 3. Store in AWS Secrets Manager (or equivalent)
aws secretsmanager create-secret \
    --name ticker-service/db-password \
    --description "Ticker service database password" \
    --secret-string "{\"password\":\"$NEW_PASSWORD\"}"

# 4. Test new password
psql -U stocksuser -h localhost -d stocksblitz -c "SELECT 1;"

# 5. Remove from .env and config.py
rm .env
echo ".env" >> .gitignore
echo "*.env" >> .gitignore

# 6. Update config.py to fetch from Secrets Manager
# (See implementation below)
```

**Implementation:**
```python
# app/config.py
import boto3
from functools import lru_cache

@lru_cache()
def get_db_password_from_secrets_manager() -> str:
    """Fetch database password from AWS Secrets Manager"""
    client = boto3.client('secretsmanager', region_name='us-east-1')
    response = client.get_secret_value(SecretId='ticker-service/db-password')
    secret = json.loads(response['SecretString'])
    return secret['password']

class Settings(BaseSettings):
    instrument_db_password: str = Field(
        default_factory=get_db_password_from_secrets_manager,
        description="Database password (loaded from AWS Secrets Manager)"
    )
```

**Verification:**
```bash
# Ensure service still connects to database
python -c "from app.config import settings; print('Password loaded:', len(settings.instrument_db_password))"

# Should output: Password loaded: 44 (or similar, NOT 13 for 'stocksblitz123')
```

---

### Task 2: Revoke and Re-issue Kite Access Token (30 minutes)

**Current Issue (CVE-TICKER-002):**
```json
// tokens/kite_token_primary.json
{
  "access_token": "drDsWGIPELBQEunYJDZV6dGJ3YJ3WnEM",
  "expires_at": "2025-11-09T07:30:00"
}
```

**Actions:**
```bash
# 1. Login to Kite Connect dashboard
# Visit: https://kite.trade/apps/dashboard

# 2. Revoke all active sessions
# Click "Revoke all sessions" button

# 3. Generate new access token
# Follow Kite Connect OAuth flow to get new token

# 4. Store encrypted token in database (not files!)
# Use encrypted_credentials table

# 5. Remove tokens directory from git
rm -rf tokens/
echo "tokens/" >> .gitignore

# 6. Verify token still works
python -c "from app.kite.client import KiteClient; client = KiteClient('primary'); print(client.profile())"
```

**Implementation:**
```python
# app/token_manager.py (NEW FILE)
from cryptography.fernet import Fernet
from app.config import settings

class SecureTokenManager:
    def __init__(self):
        # Encryption key stored in Secrets Manager
        self.cipher = Fernet(settings.encryption_key.encode())

    async def store_token(self, account_id: str, access_token: str):
        """Store token encrypted in database"""
        encrypted_token = self.cipher.encrypt(access_token.encode())

        async with db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO kite_tokens (account_id, encrypted_token, created_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (account_id)
                DO UPDATE SET encrypted_token = $2, updated_at = NOW()
            """, account_id, encrypted_token)

    async def retrieve_token(self, account_id: str) -> str:
        """Retrieve and decrypt token"""
        async with db_pool.acquire() as conn:
            encrypted_token = await conn.fetchval(
                "SELECT encrypted_token FROM kite_tokens WHERE account_id = $1",
                account_id
            )

        if not encrypted_token:
            raise ValueError(f"No token found for account {account_id}")

        return self.cipher.decrypt(encrypted_token).decode()
```

---

### Task 3: Replace Base64 with Proper Encryption (2 hours)

**Current Issue (CVE-TICKER-003):**
```python
# app/database_loader.py:82-85
# TODO: Replace with KMS decryption for production
decoded_bytes = base64.b64decode(encrypted_value)  # NOT encryption!
return decoded_bytes.decode('utf-8')
```

**Actions:**
```python
# 1. Implement AES-256-GCM encryption with KMS
# app/crypto.py (NEW FILE)

import boto3
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from typing import bytes

class KMSCredentialEncryption:
    """Proper encryption using AWS KMS for key management"""

    def __init__(self, kms_key_id: str):
        self.kms_client = boto3.client('kms')
        self.kms_key_id = kms_key_id

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt credential using KMS-managed data key"""
        # 1. Generate data encryption key from KMS
        response = self.kms_client.generate_data_key(
            KeyId=self.kms_key_id,
            KeySpec='AES_256'
        )

        data_key = response['Plaintext']
        encrypted_data_key = response['CiphertextBlob']

        # 2. Encrypt credential with data key (AES-256-GCM)
        aesgcm = AESGCM(data_key)
        nonce = os.urandom(12)  # 96-bit nonce
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)

        # 3. Return: encrypted_data_key + nonce + ciphertext
        # Format: [256 bytes: encrypted key][12 bytes: nonce][N bytes: ciphertext]
        return encrypted_data_key + nonce + ciphertext

    def decrypt(self, encrypted_blob: bytes) -> str:
        """Decrypt credential using KMS"""
        # 1. Extract components
        encrypted_data_key = encrypted_blob[:256]
        nonce = encrypted_blob[256:268]
        ciphertext = encrypted_blob[268:]

        # 2. Decrypt data key using KMS
        response = self.kms_client.decrypt(
            CiphertextBlob=encrypted_data_key
        )
        data_key = response['Plaintext']

        # 3. Decrypt credential
        aesgcm = AESGCM(data_key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)

        return plaintext.decode()

# 2. Migration script to re-encrypt existing credentials
# scripts/migrate_credentials_to_kms.py

async def migrate_credentials():
    """Re-encrypt all base64 credentials with KMS"""
    kms_encryptor = KMSCredentialEncryption('arn:aws:kms:us-east-1:ACCOUNT:key/KEY_ID')

    async with db_pool.acquire() as conn:
        # Get all accounts with base64-encoded credentials
        accounts = await conn.fetch("SELECT * FROM kite_accounts")

        for account in accounts:
            # Decode old base64 values
            old_api_key = base64.b64decode(account['api_key_encrypted']).decode()
            old_api_secret = base64.b64decode(account['api_secret_encrypted']).decode()
            old_totp = base64.b64decode(account['totp_secret_encrypted']).decode()

            # Re-encrypt with KMS
            new_api_key = kms_encryptor.encrypt(old_api_key)
            new_api_secret = kms_encryptor.encrypt(old_api_secret)
            new_totp = kms_encryptor.encrypt(old_totp)

            # Update database
            await conn.execute("""
                UPDATE kite_accounts
                SET api_key_encrypted = $1,
                    api_secret_encrypted = $2,
                    totp_secret_encrypted = $3,
                    encryption_version = 'KMS_AES256_GCM'
                WHERE account_id = $4
            """, new_api_key, new_api_secret, new_totp, account['account_id'])

            print(f"Migrated account: {account['account_id']}")

# 3. Update database_loader.py
# app/database_loader.py

from app.crypto import KMSCredentialEncryption

kms_encryptor = KMSCredentialEncryption(settings.kms_key_id)

def decrypt_credential(encrypted_value: bytes) -> str:
    """Decrypt credential using KMS (replaces base64 decode)"""
    return kms_encryptor.decrypt(encrypted_value)
```

**Migration Execution:**
```bash
# Run migration in staging first
python scripts/migrate_credentials_to_kms.py --dry-run

# Verify decryption works
python scripts/migrate_credentials_to_kms.py --verify

# Run actual migration
python scripts/migrate_credentials_to_kms.py --execute

# Verify service still works
pytest tests/integration/test_kite_client.py -v
```

---

### Task 4: Add CORS Configuration (30 minutes)

**Current Issue (CVE-TICKER-004):**
No CORS middleware configured, allowing cross-origin attacks.

**Implementation:**
```python
# app/main.py - Add after app initialization

from fastapi.middleware.cors import CORSMiddleware

# CORS configuration
if settings.environment in ("production", "staging"):
    # Production: Strict whitelist
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://yourdomain.com",
            "https://app.yourdomain.com",
            "https://dashboard.yourdomain.com"
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key"],
        expose_headers=["X-Request-ID"],
        max_age=3600,
    )
else:
    # Development: Allow localhost
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

**Verification:**
```bash
# Test CORS policy rejects unknown origins
curl -H "Origin: https://evil.com" \
     -H "Access-Control-Request-Method: POST" \
     -X OPTIONS \
     https://ticker-service.example.com/orders

# Should NOT return Access-Control-Allow-Origin header

# Test CORS policy allows whitelisted origins
curl -H "Origin: https://yourdomain.com" \
     -H "Access-Control-Request-Method: POST" \
     -X OPTIONS \
     https://ticker-service.example.com/orders

# Should return: Access-Control-Allow-Origin: https://yourdomain.com
```

---

### Task 5: Clean Git History (1 hour)

**Actions:**
```bash
# WARNING: This rewrites git history. Coordinate with team!

# 1. Backup repository first
git clone --mirror /path/to/repo /path/to/repo-backup

# 2. Remove .env file from history
git filter-repo --path .env --invert-paths

# 3. Remove tokens/ directory from history
git filter-repo --path tokens/ --invert-paths

# 4. Replace hardcoded password in all commits
cat > replacements.txt << EOF
stocksblitz123==>REDACTED_PASSWORD
drDsWGIPELBQEunYJDZV6dGJ3YJ3WnEM==>REDACTED_TOKEN
EOF

git filter-repo --replace-text replacements.txt

# 5. Force push (coordinate with team!)
git push --force --all origin
git push --force --tags origin

# 6. Verify secrets removed
git log --all -S "stocksblitz123" | wc -l
# Expected: 0

git log --all -S "drDsWGIPELBQEunYJDZV6dGJ3YJ3WnEM" | wc -l
# Expected: 0

# 7. Notify team to re-clone repository
echo "IMPORTANT: All team members must re-clone the repository"
echo "Old clones contain exposed secrets in git history"
```

---

## Testing & Verification

### Verification Checklist

```bash
# 1. Verify database connection works with new password
python -c "from app.database import db_pool; import asyncio; asyncio.run(db_pool.execute('SELECT 1'))"

# 2. Verify Kite token retrieval works
python -c "from app.kite.client import get_client; client = get_client('primary'); print(client.profile())"

# 3. Verify encrypted credentials decrypt correctly
python -c "from app.crypto import KMSCredentialEncryption; e = KMSCredentialEncryption('KEY_ID'); ct = e.encrypt('test'); pt = e.decrypt(ct); assert pt == 'test'"

# 4. Verify CORS policy
curl -I -H "Origin: https://evil.com" https://ticker-service.example.com/orders | grep Access-Control

# 5. Verify no secrets in git history
git log --all -S "stocksblitz123" | wc -l  # Should be 0
git log --all -S "drDsWGIPELBQEunYJDZV6dGJ3YJ3WnEM" | wc -l  # Should be 0

# 6. Run full test suite
pytest tests/ -v

# 7. Deploy to staging and validate
# (See deployment checklist)
```

---

## Acceptance Criteria

- [ ] Database password rotated and stored in AWS Secrets Manager
- [ ] Service connects to database using password from Secrets Manager
- [ ] Kite access token revoked and new token stored encrypted in database
- [ ] All credentials encrypted with AES-256-GCM (not base64)
- [ ] Migration script tested and executed
- [ ] CORS middleware configured with whitelist
- [ ] Git history cleaned of all secrets (verified)
- [ ] `.gitignore` updated to prevent future exposure
- [ ] Full test suite passes
- [ ] Staging deployment successful
- [ ] Security team sign-off obtained

---

## Rollback Plan

If issues discovered after deployment:

```bash
# Emergency rollback for database password
# 1. Restore old password temporarily
ALTER USER stocksuser WITH PASSWORD 'stocksblitz123';

# 2. Revert config.py changes
git revert <commit_hash>

# 3. Redeploy old version
kubectl rollout undo deployment/ticker-service
```

**NOTE:** Rollback should only be used in emergency. The exposed secrets MUST be rotated permanently.

---

## Sign-Off

- [ ] Security Engineer: _____________________ Date: _____
- [ ] DevOps Lead: _____________________ Date: _____
- [ ] Engineering Director: _____________________ Date: _____

**Deployment Blocked Until Signed**
