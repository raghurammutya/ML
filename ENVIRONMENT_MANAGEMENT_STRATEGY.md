# Environment Management Strategy - Multi-Environment Single Server

**System**: Quantagro Trading Platform (tradingview-viz)
**Challenge**: Single server hosting dev, staging, and production via port differentiation
**Date**: 2025-11-09

---

## 🎯 Executive Summary

This document provides a comprehensive strategy for managing multiple environments (dev, staging, production) on a single server, including:
- Port allocation strategy
- Configuration management
- Database segregation
- Docker Compose orchestration
- Firewall rules
- Nginx reverse proxy
- CI/CD with GitHub Actions
- Migration path to multi-server architecture

---

## 📊 Current State Assessment

### Issues Identified
1. ❌ **No port allocation strategy** - Ad-hoc port assignment
2. ❌ **Mixed configurations** - Single .env file for all environments
3. ❌ **Shared infrastructure** - Same Redis/PostgreSQL for all environments
4. ❌ **No environment isolation** - Services can interfere with each other
5. ❌ **Manual deployment** - No automated environment switching
6. ❌ **Security risks** - Production exposed on same network as dev

---

## 🏗️ Proposed Architecture

### Port Allocation Strategy

```
Port Range Allocation (Systematic):

Development (8000-8099):
- 8000: ticker_service_dev
- 8001: user_service_dev
- 8002: backend_dev
- 8003: frontend_dev (Vite dev server)
- 8004: pgAdmin_dev
- 8010: redis_dev (6379 internal → 8010 exposed)
- 8011: postgres_dev (5432 internal → 8011 exposed)
- 8020-8029: Reserved for future dev services

Staging (8100-8199):
- 8100: ticker_service_staging
- 8101: user_service_staging
- 8102: backend_staging
- 8103: frontend_staging
- 8104: pgAdmin_staging
- 8110: redis_staging (6379 internal → 8110 exposed)
- 8111: postgres_staging (5432 internal → 8111 exposed)
- 8120-8129: Reserved for future staging services

Production (8200-8299):
- 8200: ticker_service_prod
- 8201: user_service_prod
- 8202: backend_prod
- 8203: frontend_prod (static, via Nginx)
- 8204: pgAdmin_prod (restricted access)
- 8210: redis_prod (internal only, no external port)
- 8211: postgres_prod (internal only, no external port)
- 8220-8229: Reserved for future production services

Monitoring & Utilities (8300-8399):
- 8300: Prometheus
- 8301: Grafana
- 8302: Alertmanager
- 8310: Log aggregation (ELK/Loki)
- 8320: CI/CD webhooks

Public Facing (80, 443, via Nginx):
- 80 → 443 (HTTP → HTTPS redirect)
- 443 → Environment routing based on domain/path:
  - dev.stocksblitz.com → dev services
  - staging.stocksblitz.com → staging services
  - stocksblitz.com → production services
```

### Port Registry File

Create `infrastructure/port-registry.yaml`:

```yaml
# Port Allocation Registry
# Single source of truth for all port assignments

version: "1.0"
last_updated: "2025-11-09"

environments:
  development:
    range: "8000-8099"
    services:
      ticker_service:
        port: 8000
        internal_port: 8080
        protocol: http
        exposed: true
      user_service:
        port: 8001
        internal_port: 8001
        protocol: http
        exposed: true
      backend:
        port: 8002
        internal_port: 3000
        protocol: http
        exposed: true
      frontend:
        port: 8003
        internal_port: 5173
        protocol: http
        exposed: true
      pgadmin:
        port: 8004
        internal_port: 80
        protocol: http
        exposed: true
      redis:
        port: 8010
        internal_port: 6379
        protocol: tcp
        exposed: true  # Dev only
      postgres:
        port: 8011
        internal_port: 5432
        protocol: tcp
        exposed: true  # Dev only

  staging:
    range: "8100-8199"
    services:
      ticker_service:
        port: 8100
        internal_port: 8080
        protocol: http
        exposed: true
      user_service:
        port: 8101
        internal_port: 8001
        protocol: http
        exposed: true
      backend:
        port: 8102
        internal_port: 3000
        protocol: http
        exposed: true
      frontend:
        port: 8103
        internal_port: 80  # Static build
        protocol: http
        exposed: true
      pgadmin:
        port: 8104
        internal_port: 80
        protocol: http
        exposed: true
      redis:
        port: 8110
        internal_port: 6379
        protocol: tcp
        exposed: false  # Internal only
      postgres:
        port: 8111
        internal_port: 5432
        protocol: tcp
        exposed: false  # Internal only

  production:
    range: "8200-8299"
    services:
      ticker_service:
        port: 8200
        internal_port: 8080
        protocol: http
        exposed: false  # Via Nginx only
      user_service:
        port: 8201
        internal_port: 8001
        protocol: http
        exposed: false  # Via Nginx only
      backend:
        port: 8202
        internal_port: 3000
        protocol: http
        exposed: false  # Via Nginx only
      frontend:
        port: 8203
        internal_port: 80
        protocol: http
        exposed: false  # Via Nginx only
      pgadmin:
        port: 8204
        internal_port: 80
        protocol: http
        exposed: false  # VPN/SSH tunnel only
      redis:
        port: null  # Internal Docker network only
        internal_port: 6379
        protocol: tcp
        exposed: false
      postgres:
        port: null  # Internal Docker network only
        internal_port: 5432
        protocol: tcp
        exposed: false

  monitoring:
    range: "8300-8399"
    services:
      prometheus:
        port: 8300
        internal_port: 9090
        protocol: http
        exposed: false  # VPN/SSH tunnel only
      grafana:
        port: 8301
        internal_port: 3000
        protocol: http
        exposed: true  # Public dashboards
      alertmanager:
        port: 8302
        internal_port: 9093
        protocol: http
        exposed: false
```

---

## 🔧 Configuration Management Strategy

### Directory Structure

```
tradingview-viz/
├── infrastructure/
│   ├── port-registry.yaml                    # Port allocation registry
│   ├── environments/
│   │   ├── dev/
│   │   │   ├── .env                          # Development environment variables
│   │   │   ├── docker-compose.yml            # Dev-specific compose
│   │   │   └── docker-compose.override.yml   # Local developer overrides
│   │   ├── staging/
│   │   │   ├── .env                          # Staging environment variables
│   │   │   └── docker-compose.yml            # Staging-specific compose
│   │   └── production/
│   │       ├── .env.template                 # Template (secrets in vault)
│   │       └── docker-compose.yml            # Production compose
│   ├── shared/
│   │   ├── docker-compose.common.yml         # Shared service definitions
│   │   └── .env.common                       # Common non-sensitive vars
│   ├── nginx/
│   │   ├── nginx.conf                        # Main Nginx config
│   │   ├── sites-available/
│   │   │   ├── dev.conf
│   │   │   ├── staging.conf
│   │   │   └── production.conf
│   │   └── ssl/                              # SSL certificates
│   ├── firewall/
│   │   ├── ufw-rules.sh                      # UFW firewall rules
│   │   └── iptables-rules.sh                 # Alternative iptables rules
│   └── scripts/
│       ├── switch-env.sh                     # Environment switcher
│       ├── deploy-env.sh                     # Deployment script
│       ├── backup-db.sh                      # Database backup
│       └── restore-db.sh                     # Database restore
├── .github/
│   └── workflows/
│       ├── deploy-dev.yml                    # Auto-deploy to dev
│       ├── deploy-staging.yml                # Deploy to staging (manual)
│       └── deploy-production.yml             # Deploy to production (manual)
└── docs/
    └── ENVIRONMENT_MANAGEMENT.md             # This document
```

### Environment Variables Strategy

**1. Common Variables** (`infrastructure/shared/.env.common`):
```bash
# Common variables across all environments
PROJECT_NAME=quantagro-trading
COMPOSE_PROJECT_NAME=${PROJECT_NAME}-${ENVIRONMENT}

# Timezone
TZ=Asia/Kolkata

# Log levels (override per environment)
DEFAULT_LOG_LEVEL=INFO

# Non-sensitive defaults
MARKET_TIMEZONE=Asia/Kolkata
MARKET_OPEN_TIME=09:15:00
MARKET_CLOSE_TIME=15:30:00
```

**2. Development Environment** (`infrastructure/environments/dev/.env`):
```bash
# Environment identifier
ENVIRONMENT=development
ENV_SHORT=dev

# Port assignments (from port-registry.yaml)
TICKER_SERVICE_PORT=8000
USER_SERVICE_PORT=8001
BACKEND_PORT=8002
FRONTEND_PORT=8003
PGADMIN_PORT=8004
REDIS_PORT=8010
POSTGRES_PORT=8011

# Database configuration
POSTGRES_HOST=postgres_dev
POSTGRES_PORT=5432
POSTGRES_DB=stocksblitz_dev
POSTGRES_USER=stocksblitz_dev
POSTGRES_PASSWORD=dev_password_change_me

# Redis configuration
REDIS_HOST=redis_dev
REDIS_PORT=6379
REDIS_PASSWORD=dev_redis_password

# Service URLs (internal Docker network)
TICKER_SERVICE_URL=http://ticker_service_dev:8080
USER_SERVICE_URL=http://user_service_dev:8001
BACKEND_URL=http://backend_dev:3000

# External URLs (for browser access)
TICKER_SERVICE_EXTERNAL_URL=http://dev.stocksblitz.com:8000
USER_SERVICE_EXTERNAL_URL=http://dev.stocksblitz.com:8001
BACKEND_EXTERNAL_URL=http://dev.stocksblitz.com:8002
FRONTEND_EXTERNAL_URL=http://dev.stocksblitz.com:8003

# Security (relaxed for dev)
API_KEY_ENABLED=false
HTTPS_REQUIRED=false
CORS_ALLOWED_ORIGINS=*

# Debugging
DEBUG=true
LOG_LEVEL=DEBUG
ENABLE_PROFILING=true

# Mock data (for development)
ENABLE_MOCK_DATA=true
MOCK_MARKET_HOURS=true

# Secrets (not sensitive in dev)
ENCRYPTION_KEY=dev_encryption_key_32_bytes_long_12345678
API_KEY=dev_api_key_not_secret

# Kite Connect (sandbox credentials)
KITE_API_KEY=dev_kite_api_key
KITE_API_SECRET=dev_kite_api_secret
```

**3. Staging Environment** (`infrastructure/environments/staging/.env`):
```bash
# Environment identifier
ENVIRONMENT=staging
ENV_SHORT=staging

# Port assignments
TICKER_SERVICE_PORT=8100
USER_SERVICE_PORT=8101
BACKEND_PORT=8102
FRONTEND_PORT=8103
PGADMIN_PORT=8104
REDIS_PORT=8110  # Not exposed externally
POSTGRES_PORT=8111  # Not exposed externally

# Database configuration
POSTGRES_HOST=postgres_staging
POSTGRES_PORT=5432
POSTGRES_DB=stocksblitz_staging
POSTGRES_USER=stocksblitz_staging
POSTGRES_PASSWORD=${POSTGRES_STAGING_PASSWORD}  # From secrets manager

# Redis configuration
REDIS_HOST=redis_staging
REDIS_PORT=6379
REDIS_PASSWORD=${REDIS_STAGING_PASSWORD}

# Service URLs (internal)
TICKER_SERVICE_URL=http://ticker_service_staging:8080
USER_SERVICE_URL=http://user_service_staging:8001
BACKEND_URL=http://backend_staging:3000

# External URLs (via Nginx)
TICKER_SERVICE_EXTERNAL_URL=https://staging.stocksblitz.com/ticker
USER_SERVICE_EXTERNAL_URL=https://staging.stocksblitz.com/user
BACKEND_EXTERNAL_URL=https://staging.stocksblitz.com/api
FRONTEND_EXTERNAL_URL=https://staging.stocksblitz.com

# Security (production-like)
API_KEY_ENABLED=true
HTTPS_REQUIRED=true
CORS_ALLOWED_ORIGINS=https://staging.stocksblitz.com

# Debugging (limited)
DEBUG=false
LOG_LEVEL=INFO
ENABLE_PROFILING=false

# Mock data (disabled)
ENABLE_MOCK_DATA=false
MOCK_MARKET_HOURS=false

# Secrets (from secrets manager)
ENCRYPTION_KEY=${ENCRYPTION_KEY_STAGING}
API_KEY=${API_KEY_STAGING}

# Kite Connect (test account)
KITE_API_KEY=${KITE_API_KEY_STAGING}
KITE_API_SECRET=${KITE_API_SECRET_STAGING}
```

**4. Production Environment** (`infrastructure/environments/production/.env.template`):
```bash
# ⚠️ TEMPLATE ONLY - Actual secrets stored in AWS Secrets Manager / HashiCorp Vault
# Never commit actual production .env file to Git

# Environment identifier
ENVIRONMENT=production
ENV_SHORT=prod

# Port assignments (internal only, Nginx handles external)
TICKER_SERVICE_PORT=8200
USER_SERVICE_PORT=8201
BACKEND_PORT=8202
FRONTEND_PORT=8203
PGADMIN_PORT=8204
# Redis and Postgres: Docker network only, no host ports

# Database configuration
POSTGRES_HOST=postgres_prod
POSTGRES_PORT=5432
POSTGRES_DB=stocksblitz_prod
POSTGRES_USER=stocksblitz_prod
POSTGRES_PASSWORD=${POSTGRES_PROD_PASSWORD}  # From secrets manager

# Redis configuration
REDIS_HOST=redis_prod
REDIS_PORT=6379
REDIS_PASSWORD=${REDIS_PROD_PASSWORD}

# Service URLs (internal Docker network)
TICKER_SERVICE_URL=http://ticker_service_prod:8080
USER_SERVICE_URL=http://user_service_prod:8001
BACKEND_URL=http://backend_prod:3000

# External URLs (public HTTPS via Nginx)
TICKER_SERVICE_EXTERNAL_URL=https://stocksblitz.com/ticker
USER_SERVICE_EXTERNAL_URL=https://stocksblitz.com/user
BACKEND_EXTERNAL_URL=https://stocksblitz.com/api
FRONTEND_EXTERNAL_URL=https://stocksblitz.com

# Security (strict)
API_KEY_ENABLED=true
HTTPS_REQUIRED=true
CORS_ALLOWED_ORIGINS=https://stocksblitz.com,https://app.stocksblitz.com

# Debugging (disabled)
DEBUG=false
LOG_LEVEL=WARNING
ENABLE_PROFILING=false

# Mock data (disabled)
ENABLE_MOCK_DATA=false
MOCK_MARKET_HOURS=false

# Secrets (loaded from secrets manager at runtime)
ENCRYPTION_KEY=${ENCRYPTION_KEY_PROD}
API_KEY=${API_KEY_PROD}

# Kite Connect (production account)
KITE_API_KEY=${KITE_API_KEY_PROD}
KITE_API_SECRET=${KITE_API_SECRET_PROD}

# Monitoring
SENTRY_DSN=${SENTRY_DSN}
PROMETHEUS_ENABLED=true
GRAFANA_ENABLED=true

# Alerting
ALERT_EMAIL=${ALERT_EMAIL}
PAGERDUTY_KEY=${PAGERDUTY_KEY}
```

---

## 🐳 Docker Compose Strategy

### Shared Service Definitions

**`infrastructure/shared/docker-compose.common.yml`**:

```yaml
# Common service definitions inherited by all environments
version: '3.8'

x-common-service: &common-service
  restart: unless-stopped
  logging:
    driver: "json-file"
    options:
      max-size: "10m"
      max-file: "3"
  networks:
    - ${ENV_SHORT:-dev}_network

x-healthcheck-defaults: &healthcheck-defaults
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s

services:
  # Base ticker_service definition
  ticker_service:
    <<: *common-service
    image: ticker_service:${ENV_SHORT:-dev}
    build:
      context: ../../ticker_service
      dockerfile: Dockerfile
      args:
        - ENVIRONMENT=${ENVIRONMENT}
    env_file:
      - ../shared/.env.common
      - .env
    healthcheck:
      <<: *healthcheck-defaults
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
    depends_on:
      - postgres
      - redis

  # Base user_service definition
  user_service:
    <<: *common-service
    image: user_service:${ENV_SHORT:-dev}
    build:
      context: ../../user_service
      dockerfile: Dockerfile
    env_file:
      - ../shared/.env.common
      - .env
    healthcheck:
      <<: *healthcheck-defaults
      test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
    depends_on:
      - postgres

  # Base PostgreSQL definition
  postgres:
    <<: *common-service
    image: timescale/timescaledb:latest-pg15
    env_file:
      - .env
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ../../database/init:/docker-entrypoint-initdb.d
    healthcheck:
      <<: *healthcheck-defaults
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]

  # Base Redis definition
  redis:
    <<: *common-service
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    healthcheck:
      <<: *healthcheck-defaults
      test: ["CMD", "redis-cli", "--raw", "incr", "ping"]

networks:
  default:
    name: ${ENV_SHORT:-dev}_network
    driver: bridge

volumes:
  postgres_data:
    name: ${ENV_SHORT:-dev}_postgres_data
  redis_data:
    name: ${ENV_SHORT:-dev}_redis_data
```

### Environment-Specific Compose Files

**`infrastructure/environments/dev/docker-compose.yml`**:

```yaml
version: '3.8'

# Development environment - relaxed security, all ports exposed
# Extends: infrastructure/shared/docker-compose.common.yml

include:
  - ../../shared/docker-compose.common.yml

services:
  ticker_service:
    container_name: ticker_service_dev
    ports:
      - "${TICKER_SERVICE_PORT}:8080"  # 8000:8080
    environment:
      - ENVIRONMENT=development
    volumes:
      # Hot reload for development
      - ../../../ticker_service/app:/app/app:ro
      - ticker_logs:/app/logs

  user_service:
    container_name: user_service_dev
    ports:
      - "${USER_SERVICE_PORT}:8001"  # 8001:8001
    volumes:
      - ../../../user_service:/app:ro
      - user_logs:/app/logs

  backend:
    container_name: backend_dev
    image: backend:dev
    build:
      context: ../../../backend
      dockerfile: Dockerfile
    ports:
      - "${BACKEND_PORT}:3000"  # 8002:3000
    env_file:
      - ../../shared/.env.common
      - .env
    volumes:
      - ../../../backend:/app:ro
    depends_on:
      - postgres
      - ticker_service
      - user_service

  frontend:
    container_name: frontend_dev
    image: frontend:dev
    build:
      context: ../../../frontend
      dockerfile: Dockerfile.dev
    ports:
      - "${FRONTEND_PORT}:5173"  # 8003:5173 (Vite dev server)
    env_file:
      - .env
    volumes:
      - ../../../frontend:/app:ro
      - /app/node_modules  # Exclude node_modules

  postgres:
    container_name: postgres_dev
    ports:
      - "${POSTGRES_PORT}:5432"  # 8011:5432 (exposed for dev tools)
    environment:
      - POSTGRES_DB=stocksblitz_dev
      - POSTGRES_USER=stocksblitz_dev

  redis:
    container_name: redis_dev
    ports:
      - "${REDIS_PORT}:6379"  # 8010:6379 (exposed for dev tools)

  pgadmin:
    container_name: pgadmin_dev
    image: dpage/pgadmin4:latest
    ports:
      - "${PGADMIN_PORT}:80"  # 8004:80
    environment:
      - PGADMIN_DEFAULT_EMAIL=admin@stocksblitz.com
      - PGADMIN_DEFAULT_PASSWORD=dev_admin_password
    volumes:
      - pgadmin_data:/var/lib/pgadmin
    depends_on:
      - postgres

volumes:
  ticker_logs:
    name: dev_ticker_logs
  user_logs:
    name: dev_user_logs
  pgadmin_data:
    name: dev_pgadmin_data
```

**`infrastructure/environments/staging/docker-compose.yml`**:

```yaml
version: '3.8'

# Staging environment - production-like, limited exposure

include:
  - ../../shared/docker-compose.common.yml

services:
  ticker_service:
    container_name: ticker_service_staging
    ports:
      - "127.0.0.1:${TICKER_SERVICE_PORT}:8080"  # Localhost only
    environment:
      - ENVIRONMENT=staging

  user_service:
    container_name: user_service_staging
    ports:
      - "127.0.0.1:${USER_SERVICE_PORT}:8001"

  backend:
    container_name: backend_staging
    image: backend:staging
    build:
      context: ../../../backend
      dockerfile: Dockerfile
      args:
        - NODE_ENV=staging
    ports:
      - "127.0.0.1:${BACKEND_PORT}:3000"
    env_file:
      - ../../shared/.env.common
      - .env

  frontend:
    container_name: frontend_staging
    image: frontend:staging
    build:
      context: ../../../frontend
      dockerfile: Dockerfile
      args:
        - NODE_ENV=staging
    ports:
      - "127.0.0.1:${FRONTEND_PORT}:80"
    env_file:
      - .env

  postgres:
    container_name: postgres_staging
    # No external port - Docker network only
    environment:
      - POSTGRES_DB=stocksblitz_staging
      - POSTGRES_USER=stocksblitz_staging

  redis:
    container_name: redis_staging
    # No external port - Docker network only

  pgadmin:
    container_name: pgadmin_staging
    image: dpage/pgadmin4:latest
    ports:
      - "127.0.0.1:${PGADMIN_PORT}:80"  # SSH tunnel only
    environment:
      - PGADMIN_DEFAULT_EMAIL=admin@stocksblitz.com
      - PGADMIN_DEFAULT_PASSWORD=${PGADMIN_STAGING_PASSWORD}
    volumes:
      - pgadmin_data:/var/lib/pgadmin

volumes:
  pgadmin_data:
    name: staging_pgadmin_data
```

**`infrastructure/environments/production/docker-compose.yml`**:

```yaml
version: '3.8'

# Production environment - maximum security, no external ports

include:
  - ../../shared/docker-compose.common.yml

services:
  ticker_service:
    container_name: ticker_service_prod
    # No ports section - Nginx reverse proxy only
    environment:
      - ENVIRONMENT=production
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '0.5'
          memory: 1G

  user_service:
    container_name: user_service_prod
    # No ports section
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 2G

  backend:
    container_name: backend_prod
    image: backend:prod
    build:
      context: ../../../backend
      dockerfile: Dockerfile
      args:
        - NODE_ENV=production
    # No ports section
    env_file:
      - ../../shared/.env.common
      - .env
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G

  frontend:
    container_name: frontend_prod
    image: frontend:prod
    build:
      context: ../../../frontend
      dockerfile: Dockerfile
      args:
        - NODE_ENV=production
    # No ports section
    env_file:
      - .env

  postgres:
    container_name: postgres_prod
    # No ports section - Docker network only
    environment:
      - POSTGRES_DB=stocksblitz_prod
      - POSTGRES_USER=stocksblitz_prod
    deploy:
      resources:
        limits:
          cpus: '4.0'
          memory: 8G

  redis:
    container_name: redis_prod
    # No ports section - Docker network only
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 2G

  pgadmin:
    container_name: pgadmin_prod
    image: dpage/pgadmin4:latest
    # No ports section - VPN/SSH tunnel only
    environment:
      - PGADMIN_DEFAULT_EMAIL=${PGADMIN_EMAIL}
      - PGADMIN_DEFAULT_PASSWORD=${PGADMIN_PROD_PASSWORD}
    volumes:
      - pgadmin_data:/var/lib/pgadmin

volumes:
  pgadmin_data:
    name: prod_pgadmin_data
```

---

## 🔒 Firewall Configuration

### UFW (Uncomplicated Firewall) Setup

**`infrastructure/firewall/ufw-rules.sh`**:

```bash
#!/bin/bash
# UFW Firewall Rules for Multi-Environment Setup

set -e

echo "🔒 Configuring UFW firewall rules..."

# Reset UFW to default
sudo ufw --force reset

# Default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# ============================================================================
# ESSENTIAL SERVICES
# ============================================================================

# SSH (change default port for security)
sudo ufw allow 22/tcp comment 'SSH'

# HTTP/HTTPS (Nginx reverse proxy)
sudo ufw allow 80/tcp comment 'HTTP'
sudo ufw allow 443/tcp comment 'HTTPS'

# ============================================================================
# DEVELOPMENT ENVIRONMENT (8000-8099)
# Accessible from specific IP ranges only
# ============================================================================

# Allow from office/VPN IP range (example: 203.0.113.0/24)
OFFICE_IP="203.0.113.0/24"
VPN_IP="10.8.0.0/24"

# Development services (ticker, user, backend, frontend)
for port in {8000..8003}; do
    sudo ufw allow from $OFFICE_IP to any port $port proto tcp comment "Dev service $port"
    sudo ufw allow from $VPN_IP to any port $port proto tcp comment "Dev service $port (VPN)"
done

# Development database/redis (restricted to localhost + specific IPs)
sudo ufw allow from 127.0.0.1 to any port 8010 proto tcp comment "Dev Redis (localhost)"
sudo ufw allow from 127.0.0.1 to any port 8011 proto tcp comment "Dev Postgres (localhost)"
sudo ufw allow from $OFFICE_IP to any port 8010:8011 proto tcp comment "Dev DB (office)"

# Development pgAdmin
sudo ufw allow from $OFFICE_IP to any port 8004 proto tcp comment "Dev pgAdmin"

# ============================================================================
# STAGING ENVIRONMENT (8100-8199)
# More restricted than dev
# ============================================================================

# Staging services (localhost only, accessed via Nginx)
# No direct port access from outside

# Staging pgAdmin (VPN/SSH tunnel only)
sudo ufw allow from 127.0.0.1 to any port 8104 proto tcp comment "Staging pgAdmin (SSH tunnel)"

# ============================================================================
# PRODUCTION ENVIRONMENT (8200-8299)
# Maximum security - no direct access, Nginx only
# ============================================================================

# Production services: NO direct port access
# All traffic routed through Nginx (ports 80/443)

# Production pgAdmin (VPN/SSH tunnel only)
sudo ufw allow from 127.0.0.1 to any port 8204 proto tcp comment "Prod pgAdmin (SSH tunnel)"

# ============================================================================
# MONITORING (8300-8399)
# Restricted access
# ============================================================================

# Prometheus (localhost + VPN only)
sudo ufw allow from 127.0.0.1 to any port 8300 proto tcp comment "Prometheus (localhost)"
sudo ufw allow from $VPN_IP to any port 8300 proto tcp comment "Prometheus (VPN)"

# Grafana (public access via Nginx, or direct from VPN)
sudo ufw allow from $VPN_IP to any port 8301 proto tcp comment "Grafana (VPN)"

# ============================================================================
# DOCKER
# ============================================================================

# Allow Docker daemon (if remote access needed)
# sudo ufw allow from $OFFICE_IP to any port 2375 proto tcp comment "Docker API"

# ============================================================================
# RATE LIMITING (DDoS protection)
# ============================================================================

# Limit SSH connections (max 6 attempts in 30 seconds)
sudo ufw limit 22/tcp

# Limit HTTP/HTTPS (adjust as needed)
sudo ufw limit 80/tcp
sudo ufw limit 443/tcp

# ============================================================================
# LOGGING
# ============================================================================

sudo ufw logging on
sudo ufw logging medium

# ============================================================================
# ENABLE FIREWALL
# ============================================================================

sudo ufw --force enable

echo "✅ UFW firewall rules configured successfully"
echo ""
echo "Status:"
sudo ufw status verbose
```

**Run firewall script**:
```bash
chmod +x infrastructure/firewall/ufw-rules.sh
sudo ./infrastructure/firewall/ufw-rules.sh
```

---

## 🌐 Nginx Configuration

### Main Nginx Config

**`infrastructure/nginx/nginx.conf`**:

```nginx
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 4096;
    use epoll;
    multi_accept on;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # Logging
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for" '
                    'rt=$request_time uct="$upstream_connect_time" '
                    'uht="$upstream_header_time" urt="$upstream_response_time"';

    access_log /var/log/nginx/access.log main;

    # Performance
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    client_max_body_size 100M;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml text/javascript
               application/json application/javascript application/xml+rss
               application/rss+xml font/truetype font/opentype
               application/vnd.ms-fontobject image/svg+xml;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;

    # Rate limiting zones
    limit_req_zone $binary_remote_addr zone=general:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=api:10m rate=100r/s;
    limit_req_zone $binary_remote_addr zone=auth:10m rate=5r/s;

    # Include site configurations
    include /etc/nginx/conf.d/*.conf;
    include /etc/nginx/sites-enabled/*;
}
```

### Development Environment Config

**`infrastructure/nginx/sites-available/dev.conf`**:

```nginx
# Development Environment
# Domain: dev.stocksblitz.com
# Ports: 8000-8099

upstream ticker_service_dev {
    server localhost:8000;
    keepalive 32;
}

upstream user_service_dev {
    server localhost:8001;
    keepalive 32;
}

upstream backend_dev {
    server localhost:8002;
    keepalive 32;
}

upstream frontend_dev {
    server localhost:8003;
    keepalive 32;
}

server {
    listen 80;
    server_name dev.stocksblitz.com;

    # Development: Allow HTTP (no HTTPS redirect)

    location / {
        proxy_pass http://frontend_dev;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (for Vite HMR)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location /ticker/ {
        proxy_pass http://ticker_service_dev/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location /user/ {
        proxy_pass http://user_service_dev/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api/ {
        proxy_pass http://backend_dev/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;

        # CORS for development
        add_header Access-Control-Allow-Origin * always;
        add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS" always;
        add_header Access-Control-Allow-Headers "Authorization, Content-Type" always;

        if ($request_method = OPTIONS) {
            return 204;
        }
    }
}
```

### Staging Environment Config

**`infrastructure/nginx/sites-available/staging.conf`**:

```nginx
# Staging Environment
# Domain: staging.stocksblitz.com
# Ports: 8100-8199 (internal)

upstream ticker_service_staging {
    server localhost:8100;
    keepalive 32;
}

upstream user_service_staging {
    server localhost:8101;
    keepalive 32;
}

upstream backend_staging {
    server localhost:8102;
    keepalive 32;
}

upstream frontend_staging {
    server localhost:8103;
    keepalive 32;
}

# HTTP -> HTTPS redirect
server {
    listen 80;
    server_name staging.stocksblitz.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS server
server {
    listen 443 ssl http2;
    server_name staging.stocksblitz.com;

    # SSL certificate (Let's Encrypt)
    ssl_certificate /etc/nginx/ssl/staging.stocksblitz.com/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/staging.stocksblitz.com/privkey.pem;

    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # HSTS
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    location / {
        proxy_pass http://frontend_staging;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /ticker/ {
        limit_req zone=api burst=20 nodelay;

        proxy_pass http://ticker_service_staging/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }

    location /user/ {
        limit_req zone=api burst=20 nodelay;

        proxy_pass http://user_service_staging/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        limit_req zone=api burst=50 nodelay;

        proxy_pass http://backend_staging/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
}
```

### Production Environment Config

**`infrastructure/nginx/sites-available/production.conf`**:

```nginx
# Production Environment
# Domain: stocksblitz.com, www.stocksblitz.com
# Ports: 8200-8299 (internal Docker network only)

upstream ticker_service_prod {
    server ticker_service_prod:8080;  # Docker network
    keepalive 64;
}

upstream user_service_prod {
    server user_service_prod:8001;
    keepalive 64;
}

upstream backend_prod {
    server backend_prod:3000;
    keepalive 64;
}

upstream frontend_prod {
    server frontend_prod:80;
    keepalive 64;
}

# HTTP -> HTTPS redirect
server {
    listen 80;
    server_name stocksblitz.com www.stocksblitz.com;
    return 301 https://stocksblitz.com$request_uri;
}

# www -> non-www redirect
server {
    listen 443 ssl http2;
    server_name www.stocksblitz.com;

    ssl_certificate /etc/nginx/ssl/stocksblitz.com/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/stocksblitz.com/privkey.pem;

    return 301 https://stocksblitz.com$request_uri;
}

# Main production server
server {
    listen 443 ssl http2;
    server_name stocksblitz.com;

    # SSL certificate (Let's Encrypt)
    ssl_certificate /etc/nginx/ssl/stocksblitz.com/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/stocksblitz.com/privkey.pem;

    # Modern SSL configuration
    ssl_protocols TLSv1.3;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;

    # OCSP stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    ssl_trusted_certificate /etc/nginx/ssl/stocksblitz.com/chain.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;

    # Content Security Policy
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline';" always;

    # Frontend
    location / {
        proxy_pass http://frontend_prod;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Caching for static assets
        location ~* \.(jpg|jpeg|png|gif|ico|css|js|woff|woff2|ttf|svg)$ {
            proxy_pass http://frontend_prod;
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }

    # Ticker service
    location /ticker/ {
        limit_req zone=api burst=100 nodelay;

        proxy_pass http://ticker_service_prod/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
    }

    # User service
    location /user/ {
        limit_req zone=auth burst=10 nodelay;

        proxy_pass http://user_service_prod/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Backend API
    location /api/ {
        limit_req zone=api burst=200 nodelay;

        proxy_pass http://backend_prod/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # CORS (strict)
        add_header Access-Control-Allow-Origin "https://stocksblitz.com" always;
        add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE" always;
        add_header Access-Control-Allow-Headers "Authorization, Content-Type" always;
        add_header Access-Control-Max-Age 3600 always;

        if ($request_method = OPTIONS) {
            return 204;
        }
    }

    # Health check endpoint
    location /health {
        access_log off;
        proxy_pass http://ticker_service_prod/health;
        proxy_set_header Host $host;
    }

    # Block access to sensitive paths
    location ~ /\. {
        deny all;
    }

    location ~ (\.env|\.git|\.svn|\.htaccess) {
        deny all;
    }
}
```

**Enable sites**:
```bash
sudo ln -s /etc/nginx/sites-available/dev.conf /etc/nginx/sites-enabled/
sudo ln -s /etc/nginx/sites-available/staging.conf /etc/nginx/sites-enabled/
sudo ln -s /etc/nginx/sites-available/production.conf /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 🔄 Database Migration Strategy

### Environment Switcher Script

**`infrastructure/scripts/switch-db-env.sh`**:

```bash
#!/bin/bash
# Database environment switcher with backup and validation

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
BACKUP_DIR="/var/backups/postgres"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

usage() {
    echo "Usage: $0 <source_env> <target_env>"
    echo ""
    echo "Environments: dev, staging, production"
    echo ""
    echo "Examples:"
    echo "  $0 dev staging      # Migrate dev database to staging"
    echo "  $0 staging prod     # Migrate staging database to production"
    echo ""
    exit 1
}

# Validate arguments
if [ $# -ne 2 ]; then
    usage
fi

SOURCE_ENV=$1
TARGET_ENV=$2

# Validate environments
if [[ ! "$SOURCE_ENV" =~ ^(dev|staging|production)$ ]] || [[ ! "$TARGET_ENV" =~ ^(dev|staging|production)$ ]]; then
    echo -e "${RED}Error: Invalid environment. Must be dev, staging, or production${NC}"
    usage
fi

# Confirm migration
echo -e "${YELLOW}⚠️  WARNING: This will migrate database from $SOURCE_ENV to $TARGET_ENV${NC}"
echo -e "${YELLOW}This operation will:${NC}"
echo -e "  1. Backup current $TARGET_ENV database"
echo -e "  2. Export $SOURCE_ENV database"
echo -e "  3. Import into $TARGET_ENV database"
echo -e ""
read -p "Are you sure? (type 'yes' to continue): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo -e "${RED}Migration cancelled${NC}"
    exit 1
fi

# Load environment configurations
case $SOURCE_ENV in
    dev)
        SOURCE_DB="stocksblitz_dev"
        SOURCE_USER="stocksblitz_dev"
        SOURCE_HOST="localhost"
        SOURCE_PORT="8011"
        ;;
    staging)
        SOURCE_DB="stocksblitz_staging"
        SOURCE_USER="stocksblitz_staging"
        SOURCE_HOST="localhost"
        SOURCE_PORT="8111"
        ;;
    production)
        SOURCE_DB="stocksblitz_prod"
        SOURCE_USER="stocksblitz_prod"
        SOURCE_HOST="localhost"
        SOURCE_PORT="8211"
        ;;
esac

case $TARGET_ENV in
    dev)
        TARGET_DB="stocksblitz_dev"
        TARGET_USER="stocksblitz_dev"
        TARGET_HOST="localhost"
        TARGET_PORT="8011"
        ;;
    staging)
        TARGET_DB="stocksblitz_staging"
        TARGET_USER="stocksblitz_staging"
        TARGET_HOST="localhost"
        TARGET_PORT="8111"
        ;;
    production)
        TARGET_DB="stocksblitz_prod"
        TARGET_USER="stocksblitz_prod"
        TARGET_HOST="localhost"
        TARGET_PORT="8211"
        ;;
esac

# Create backup directory
mkdir -p "$BACKUP_DIR"

echo -e "${GREEN}Step 1: Backing up target database ($TARGET_ENV)...${NC}"
PGPASSWORD=$(grep POSTGRES_PASSWORD infrastructure/environments/$TARGET_ENV/.env | cut -d '=' -f2) \
    pg_dump -h $TARGET_HOST -p $TARGET_PORT -U $TARGET_USER -Fc -f "$BACKUP_DIR/${TARGET_DB}_${TIMESTAMP}.backup" $TARGET_DB

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Backup completed: $BACKUP_DIR/${TARGET_DB}_${TIMESTAMP}.backup${NC}"
else
    echo -e "${RED}✗ Backup failed${NC}"
    exit 1
fi

echo -e "${GREEN}Step 2: Exporting source database ($SOURCE_ENV)...${NC}"
PGPASSWORD=$(grep POSTGRES_PASSWORD infrastructure/environments/$SOURCE_ENV/.env | cut -d '=' -f2) \
    pg_dump -h $SOURCE_HOST -p $SOURCE_PORT -U $SOURCE_USER -Fc -f "$BACKUP_DIR/${SOURCE_DB}_export_${TIMESTAMP}.backup" $SOURCE_DB

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Export completed${NC}"
else
    echo -e "${RED}✗ Export failed${NC}"
    exit 1
fi

echo -e "${GREEN}Step 3: Dropping target database ($TARGET_ENV)...${NC}"
PGPASSWORD=$(grep POSTGRES_PASSWORD infrastructure/environments/$TARGET_ENV/.env | cut -d '=' -f2) \
    psql -h $TARGET_HOST -p $TARGET_PORT -U $TARGET_USER -c "DROP DATABASE IF EXISTS $TARGET_DB;"

echo -e "${GREEN}Step 4: Creating fresh target database...${NC}"
PGPASSWORD=$(grep POSTGRES_PASSWORD infrastructure/environments/$TARGET_ENV/.env | cut -d '=' -f2) \
    psql -h $TARGET_HOST -p $TARGET_PORT -U $TARGET_USER -c "CREATE DATABASE $TARGET_DB OWNER $TARGET_USER;"

echo -e "${GREEN}Step 5: Importing source database into target...${NC}"
PGPASSWORD=$(grep POSTGRES_PASSWORD infrastructure/environments/$TARGET_ENV/.env | cut -d '=' -f2) \
    pg_restore -h $TARGET_HOST -p $TARGET_PORT -U $TARGET_USER -d $TARGET_DB "$BACKUP_DIR/${SOURCE_DB}_export_${TIMESTAMP}.backup"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Import completed successfully${NC}"
else
    echo -e "${RED}✗ Import failed${NC}"
    echo -e "${YELLOW}Restoring from backup...${NC}"

    # Restore from backup
    PGPASSWORD=$(grep POSTGRES_PASSWORD infrastructure/environments/$TARGET_ENV/.env | cut -d '=' -f2) \
        psql -h $TARGET_HOST -p $TARGET_PORT -U $TARGET_USER -c "DROP DATABASE IF EXISTS $TARGET_DB;"

    PGPASSWORD=$(grep POSTGRES_PASSWORD infrastructure/environments/$TARGET_ENV/.env | cut -d '=' -f2) \
        psql -h $TARGET_HOST -p $TARGET_PORT -U $TARGET_USER -c "CREATE DATABASE $TARGET_DB OWNER $TARGET_USER;"

    PGPASSWORD=$(grep POSTGRES_PASSWORD infrastructure/environments/$TARGET_ENV/.env | cut -d '=' -f2) \
        pg_restore -h $TARGET_HOST -p $TARGET_PORT -U $TARGET_USER -d $TARGET_DB "$BACKUP_DIR/${TARGET_DB}_${TIMESTAMP}.backup"

    echo -e "${GREEN}✓ Restored from backup${NC}"
    exit 1
fi

echo -e "${GREEN}Step 6: Validating migration...${NC}"
SOURCE_COUNT=$(PGPASSWORD=$(grep POSTGRES_PASSWORD infrastructure/environments/$SOURCE_ENV/.env | cut -d '=' -f2) \
    psql -h $SOURCE_HOST -p $SOURCE_PORT -U $SOURCE_USER -d $SOURCE_DB -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")

TARGET_COUNT=$(PGPASSWORD=$(grep POSTGRES_PASSWORD infrastructure/environments/$TARGET_ENV/.env | cut -d '=' -f2) \
    psql -h $TARGET_HOST -p $TARGET_PORT -U $TARGET_USER -d $TARGET_DB -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")

if [ "$SOURCE_COUNT" -eq "$TARGET_COUNT" ]; then
    echo -e "${GREEN}✓ Validation successful: $TARGET_COUNT tables migrated${NC}"
else
    echo -e "${RED}✗ Validation failed: Source has $SOURCE_COUNT tables, target has $TARGET_COUNT tables${NC}"
fi

echo -e ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Migration completed successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e ""
echo -e "Source: $SOURCE_ENV ($SOURCE_DB)"
echo -e "Target: $TARGET_ENV ($TARGET_DB)"
echo -e "Backup: $BACKUP_DIR/${TARGET_DB}_${TIMESTAMP}.backup"
echo -e ""
echo -e "${YELLOW}Next steps:${NC}"
echo -e "1. Restart target environment services"
echo -e "2. Run smoke tests"
echo -e "3. Verify data integrity"
echo -e ""
```

**Usage**:
```bash
chmod +x infrastructure/scripts/switch-db-env.sh

# Migrate dev → staging
./infrastructure/scripts/switch-db-env.sh dev staging

# Migrate staging → production (be careful!)
./infrastructure/scripts/switch-db-env.sh staging production
```

---

## 🚀 GitHub Actions CI/CD

### Development Auto-Deploy

**`.github/workflows/deploy-dev.yml`**:

```yaml
name: Deploy to Development

on:
  push:
    branches:
      - develop
      - feature/*

jobs:
  deploy-dev:
    runs-on: ubuntu-latest
    environment: development

    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Deploy to dev environment
        uses: appleboy/ssh-action@v0.1.10
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /mnt/stocksblitz-data/Quantagro/tradingview-viz
            git pull origin ${{ github.ref_name }}

            # Switch to dev environment
            cd infrastructure/environments/dev
            docker-compose down
            docker-compose up -d --build

            # Health check
            sleep 10
            curl -f http://localhost:8000/health || exit 1

            echo "✅ Development deployment successful"
```

### Staging Manual Deploy

**`.github/workflows/deploy-staging.yml`**:

```yaml
name: Deploy to Staging

on:
  workflow_dispatch:
    inputs:
      branch:
        description: 'Branch to deploy'
        required: true
        default: 'develop'

jobs:
  deploy-staging:
    runs-on: ubuntu-latest
    environment: staging

    steps:
      - name: Checkout code
        uses: actions/checkout@v3
        with:
          ref: ${{ github.event.inputs.branch }}

      - name: Run tests
        run: |
          cd ticker_service
          python3 -m pytest tests/unit/ -v

      - name: Deploy to staging
        uses: appleboy/ssh-action@v0.1.10
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /mnt/stocksblitz-data/Quantagro/tradingview-viz
            git pull origin ${{ github.event.inputs.branch }}

            # Backup staging database
            ./infrastructure/scripts/backup-db.sh staging

            # Switch to staging environment
            cd infrastructure/environments/staging
            docker-compose down
            docker-compose up -d --build

            # Health check
            sleep 15
            curl -f http://localhost:8100/health || exit 1

            echo "✅ Staging deployment successful"

      - name: Run smoke tests
        uses: appleboy/ssh-action@v0.1.10
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/tests
            ./smoke-tests-staging.sh
```

### Production Manual Deploy

**`.github/workflows/deploy-production.yml`**:

```yaml
name: Deploy to Production

on:
  workflow_dispatch:
    inputs:
      version:
        description: 'Version tag to deploy (e.g., v1.2.3)'
        required: true
      confirm:
        description: 'Type "DEPLOY TO PRODUCTION" to confirm'
        required: true

jobs:
  validate-input:
    runs-on: ubuntu-latest
    steps:
      - name: Validate confirmation
        run: |
          if [ "${{ github.event.inputs.confirm }}" != "DEPLOY TO PRODUCTION" ]; then
            echo "❌ Confirmation failed. Deployment cancelled."
            exit 1
          fi

  deploy-production:
    needs: validate-input
    runs-on: ubuntu-latest
    environment: production

    steps:
      - name: Checkout code
        uses: actions/checkout@v3
        with:
          ref: ${{ github.event.inputs.version }}

      - name: Run full test suite
        run: |
          cd ticker_service
          python3 -m pytest tests/ -v

      - name: Security scan
        run: |
          # Run security scans
          pip install bandit safety
          bandit -r ticker_service/app/
          safety check -r ticker_service/requirements.txt

      - name: Deploy to production
        uses: appleboy/ssh-action@v0.1.10
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /mnt/stocksblitz-data/Quantagro/tradingview-viz

            # Backup production database
            ./infrastructure/scripts/backup-db.sh production

            # Checkout version tag
            git fetch --tags
            git checkout ${{ github.event.inputs.version }}

            # Blue-green deployment: Start new containers
            cd infrastructure/environments/production
            docker-compose up -d --build --no-deps --scale ticker_service=2

            # Health check on new containers
            sleep 30
            curl -f http://localhost:8200/health || exit 1

            # Gradual traffic shift (via Nginx reload)
            sudo systemctl reload nginx

            # Monitor for 5 minutes
            sleep 300

            # Stop old containers
            docker-compose down --remove-orphans
            docker-compose up -d

            echo "✅ Production deployment successful"

      - name: Run smoke tests
        uses: appleboy/ssh-action@v0.1.10
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/tests
            ./smoke-tests-production.sh

      - name: Notify team
        uses: 8398a7/action-slack@v3
        with:
          status: ${{ job.status }}
          text: 'Production deployment ${{ github.event.inputs.version }} completed'
          webhook_url: ${{ secrets.SLACK_WEBHOOK }}
        if: always()
```

---

## 📋 Implementation Checklist

### Phase 1: Setup Infrastructure (Week 1)

- [ ] Create directory structure (`infrastructure/`)
- [ ] Create port registry (`port-registry.yaml`)
- [ ] Create environment-specific `.env` files
- [ ] Create shared Docker Compose base
- [ ] Create environment-specific Docker Compose files

### Phase 2: Firewall & Nginx (Week 1)

- [ ] Configure UFW firewall rules
- [ ] Create Nginx configurations (dev, staging, production)
- [ ] Obtain SSL certificates (Let's Encrypt)
- [ ] Test Nginx routing
- [ ] Configure rate limiting

### Phase 3: Database Segregation (Week 2)

- [ ] Create separate databases (dev, staging, production)
- [ ] Create database migration script
- [ ] Test database switching
- [ ] Set up automated backups
- [ ] Document restore procedure

### Phase 4: CI/CD (Week 2)

- [ ] Create GitHub Actions workflows
- [ ] Configure SSH access to server
- [ ] Set up environment secrets
- [ ] Test auto-deploy to dev
- [ ] Test manual deploy to staging/production

### Phase 5: Testing & Validation (Week 3)

- [ ] Test full dev deployment
- [ ] Test full staging deployment
- [ ] Test production deployment (dry run)
- [ ] Validate firewall rules
- [ ] Validate Nginx routing
- [ ] Test database migrations

### Phase 6: Migration to Production (Week 4)

- [ ] Final review with team
- [ ] Production deployment
- [ ] Monitor for 24 hours
- [ ] Document lessons learned

---

## 🔮 Future Improvements (Multi-Server Architecture)

When ready to scale beyond single-server:

```
Future Architecture:

┌─────────────────┐
│  Load Balancer  │ (Nginx / HAProxy / AWS ALB)
│  (SSL Offload)  │
└────────┬────────┘
         │
    ┌────┴────┬──────────┬──────────┐
    │         │          │          │
┌───▼──┐  ┌──▼──┐   ┌───▼──┐  ┌───▼──┐
│ Dev  │  │Stag │   │Prod 1│  │Prod 2│  Application Servers
│Server│  │Server   │Server│  │Server│  (Auto-scaling)
└───┬──┘  └──┬──┘   └───┬──┘  └───┬──┘
    │        │          │         │
    └────────┴──────────┴─────────┘
                 │
        ┌────────┴────────┐
        │                 │
   ┌────▼─────┐    ┌─────▼────┐
   │PostgreSQL│    │  Redis   │   Database Tier
   │  Cluster │    │  Cluster │   (Managed Services)
   │ (Primary/│    │(Sentinel)│
   │ Replica) │    │          │
   └──────────┘    └──────────┘
```

**Migration Strategy**:
1. Move databases to managed services (AWS RDS, ElastiCache)
2. Set up multiple application servers
3. Implement load balancer
4. Configure auto-scaling
5. Set up container orchestration (Kubernetes/ECS)

---

## 📚 Additional Resources

**Tools to Install**:
```bash
# Port management
sudo apt install net-tools lsof

# Database tools
sudo apt install postgresql-client redis-tools

# Monitoring
sudo apt install htop iotop nethogs

# Security
sudo apt install ufw fail2ban

# Nginx
sudo apt install nginx certbot python3-certbot-nginx
```

**Useful Commands**:
```bash
# Check which service is using a port
sudo lsof -i :8000

# List all Docker networks
docker network ls

# Check environment variables in running container
docker exec ticker_service_dev env

# Test Nginx configuration
sudo nginx -t

# Reload Nginx without downtime
sudo systemctl reload nginx

# View firewall status
sudo ufw status numbered

# Monitor real-time logs
docker-compose logs -f ticker_service

# Database connection test
PGPASSWORD=xxx psql -h localhost -p 8011 -U stocksblitz_dev -d stocksblitz_dev -c "SELECT 1"
```

---

**Document Version**: 1.0
**Last Updated**: 2025-11-09
**Status**: Production Ready
