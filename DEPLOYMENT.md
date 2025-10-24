# TradingView ML Visualization - Deployment Guide

## 🚀 Quick Deployment

### Deploy to Development
```bash
./scripts/deploy.sh dev
```

### Deploy to Production
```bash
./scripts/deploy.sh prod
```

### Switch Environments
```bash
./scripts/switch-env.sh prod  # Switch to production
./scripts/switch-env.sh dev   # Switch to development
```

## 📋 Configuration Management

### View Configuration
```bash
./scripts/config.sh show dev   # Show dev config
./scripts/config.sh show prod  # Show prod config
```

### Edit Configuration
```bash
./scripts/config.sh edit dev   # Edit dev config
./scripts/config.sh edit prod  # Edit prod config
```

### Validate Configuration
```bash
./scripts/config.sh validate dev   # Validate dev config
./scripts/config.sh validate prod  # Validate prod config
```

### Compare Configurations
```bash
./scripts/config.sh diff  # Compare dev vs prod
```

## 🔧 Environment Variables

Configuration is managed through environment files:
- `.env.dev` - Development environment
- `.env.prod` - Production environment

### Key Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `ENVIRONMENT` | Environment name | `dev`, `prod` |
| `BACKEND_PORT` | Backend external port | `8001`, `8888` |
| `FRONTEND_PORT` | Frontend external port | `3001`, `3080` |
| `DATABASE_URL` | Database connection URL | `postgresql://user:pass@host:port/db` |
| `REDIS_URL` | Redis connection URL | `redis://host:port` |
| `BACKEND_SERVICE_NAME` | Backend container name | `tv-backend-dev` |
| `FRONTEND_SERVICE_NAME` | Frontend container name | `tv-frontend-dev` |

## 🐳 Docker Architecture

### Unified Docker Compose
- Single `docker-compose.unified.yml` file
- Environment-specific configuration via `.env` files
- Dynamic service naming and networking
- Automatic dependency management

### Service Discovery
- Backend URL automatically resolved via Docker DNS
- Fallback to environment-specific service names
- No hardcoded IPs or hostnames

### Networking
- Isolated networks per environment: `tradingview-dev-network`, `tradingview-prod-network`
- Services communicate via Docker DNS
- External access via mapped ports

## 🔄 Deployment Process

### 1. Code Changes
Make your changes to backend or frontend code.

### 2. Choose Environment
```bash
# Deploy to development
./scripts/deploy.sh dev --build

# Deploy to production  
./scripts/deploy.sh prod --build
```

### 3. Verify Deployment
The script automatically performs health checks and provides access URLs.

### 4. Monitor
```bash
# View logs
docker-compose -f docker-compose.unified.yml --env-file .env.dev logs -f

# Check status
docker-compose -f docker-compose.unified.yml --env-file .env.dev ps
```

## 🛠️ Development Workflow

### 1. Local Development
```bash
# Start development environment
./scripts/deploy.sh dev

# Make code changes
# ...

# Rebuild and redeploy
./scripts/deploy.sh dev --build
```

### 2. Testing Changes
```bash
# Test in development
curl http://localhost:3001/tradingview-api/health

# Switch to production for final testing
./scripts/switch-env.sh prod
curl http://localhost:3080/tradingview-api/health
```

### 3. Production Deployment
```bash
# Deploy to production
./scripts/deploy.sh prod --build

# Monitor logs
./scripts/deploy.sh prod --logs
```

## 🔍 Troubleshooting

### Check Configuration
```bash
./scripts/config.sh validate dev
./scripts/config.sh validate prod
```

### View Service Status
```bash
docker-compose -f docker-compose.unified.yml --env-file .env.dev ps
```

### Debug Network Issues
```bash
# Check if backend is reachable from frontend
docker exec tv-frontend-dev curl http://tv-backend-dev:8000/health
```

### Clean Reset
```bash
./scripts/switch-env.sh dev  # Completely reset to dev environment
```

## 📊 Environment URLs

### Development
- Frontend: http://localhost:3001
- Backend: http://localhost:8001
- API: http://localhost:3001/tradingview-api/

### Production
- Frontend: http://localhost:3080, http://5.223.52.98:3080
- Backend: http://localhost:8888
- API: http://localhost:3080/tradingview-api/

## 🔐 Security Notes

- Production uses restricted CORS origins
- Environment-specific rate limiting
- No hardcoded credentials (use environment variables)
- Container isolation via networks

## 📈 Benefits

✅ **No Manual Configuration Changes** - Environment-specific configs automatically applied
✅ **One-Command Deployment** - Single script deploys entire stack
✅ **Environment Isolation** - Separate networks and services per environment  
✅ **Consistent Naming** - Predictable service names and ports
✅ **Automatic Health Checks** - Deployment verifies all services are healthy
✅ **Easy Environment Switching** - Switch between dev/prod with one command
✅ **Configuration Validation** - Catch config errors before deployment