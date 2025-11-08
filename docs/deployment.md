# Deployment Guide

This guide covers the deployment of the TradingView ML Visualization System across different environments.

## Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- Git
- 8GB+ RAM recommended
- 20GB+ disk space

## Environment Setup

### 1. Clone and Prepare Repository

```bash
git clone <repository-url>
cd tradingview-ml-viz
```

### 2. Environment Configuration

Create environment-specific configuration files:

```bash
# Development
cp .env.example .env.dev
# Edit .env.dev with development settings

# Staging
cp .env.example .env.staging
# Edit .env.staging with staging settings

# Production
cp .env.example .env.prod
# Edit .env.prod with production settings
```

### 3. SSL Certificates (Production/Staging)

Place SSL certificates in the appropriate directory:

```bash
# Create certificates directory
mkdir -p deployment/ssl/

# Copy your certificates
cp your-domain.crt deployment/ssl/server.crt
cp your-domain.key deployment/ssl/server.key
```

## Deployment Commands

### Development Environment

```bash
# Start development environment
./scripts/deploy.sh dev start

# View logs
./scripts/deploy.sh dev logs

# Stop services
./scripts/deploy.sh dev stop
```

**Development URLs:**
- Frontend: http://localhost:3001
- Backend API: http://localhost:8001
- Database: localhost:5433

### Staging Environment

```bash
# Deploy to staging
./scripts/deploy.sh staging deploy

# Check status
./scripts/deploy.sh staging status

# View logs
./scripts/deploy.sh staging logs backend
```

**Staging URLs:**
- Frontend: https://staging.yourdomain.com
- Backend API: https://staging.yourdomain.com/api
- Database: localhost:5434

### Production Environment

```bash
# Create backup before deployment
./scripts/deploy.sh prod backup

# Deploy to production
./scripts/deploy.sh prod deploy

# Monitor deployment
./scripts/deploy.sh prod status
./scripts/deploy.sh prod health
```

**Production URLs:**
- Frontend: https://yourdomain.com
- Backend API: https://yourdomain.com/api
- Database: localhost:5432

## Database Migration

### Initial Setup

For new environments, run the database initialization:

```bash
# Development (sample data)
python scripts/data-migration.py \
    --environment dev \
    --source-host production-db-host \
    --source-db stocksblitz_unified \
    --source-user stocksblitz \
    --source-password $PROD_DB_PASSWORD \
    --target-host localhost \
    --target-db stocksblitz_unified_dev \
    --target-user stocksblitz \
    --target-password $DEV_DB_PASSWORD \
    --redis-url redis://localhost:6380 \
    --days 30

# Staging (3 months data)
python scripts/data-migration.py \
    --environment staging \
    --source-host production-db-host \
    --source-db stocksblitz_unified \
    --source-user stocksblitz \
    --source-password $PROD_DB_PASSWORD \
    --target-host staging-db-host \
    --target-db stocksblitz_unified_staging \
    --target-user stocksblitz \
    --target-password $STAGING_DB_PASSWORD \
    --redis-url redis://staging-redis:6379 \
    --days 90
```

### Ongoing Data Sync

Start real-time data synchronization:

```bash
# Development
python scripts/real-time-data-sync.py --config config/dev-sync.json

# Staging
python scripts/real-time-data-sync.py --config config/staging-sync.json

# Production
python scripts/real-time-data-sync.py --config config/prod-sync.json
```

## CI/CD Pipeline

### GitHub Actions Setup

1. **Repository Secrets:**
   ```
   REGISTRY_USERNAME=your-github-username
   REGISTRY_PASSWORD=your-github-token
   STAGING_HOST=staging-server-ip
   STAGING_SSH_KEY=staging-server-ssh-key
   PROD_HOST=production-server-ip
   PROD_SSH_KEY=production-server-ssh-key
   DB_PASSWORD=database-password
   REDIS_PASSWORD=redis-password
   ```

2. **Workflow Triggers:**
   - Push to `develop` → Deploy to staging
   - Push to `main` → Deploy to production
   - Pull requests → Run tests

### Manual Deployment

```bash
# Build images locally
docker-compose -f deployment/docker/docker-compose.prod.yml build

# Tag and push to registry
docker tag tradingview-ml-viz-backend:latest ghcr.io/yourorg/tradingview-ml-viz-backend:latest
docker tag tradingview-ml-viz-frontend:latest ghcr.io/yourorg/tradingview-ml-viz-frontend:latest

docker push ghcr.io/yourorg/tradingview-ml-viz-backend:latest
docker push ghcr.io/yourorg/tradingview-ml-viz-frontend:latest
```

## Monitoring and Health Checks

### Health Endpoints

- **Overall Health:** `GET /health`
- **Database Health:** `GET /health/db`
- **Cache Health:** `GET /health/cache`
- **Metrics:** `GET /metrics`

### Log Monitoring

```bash
# View all logs
./scripts/deploy.sh prod logs

# View specific service logs
./scripts/deploy.sh prod logs backend
./scripts/deploy.sh prod logs frontend

# Follow logs in real-time
./scripts/deploy.sh prod logs -f backend
```

### Performance Monitoring

```bash
# Check resource usage
docker stats

# Monitor database performance
docker exec tv-postgres-prod psql -U stocksblitz -d stocksblitz_unified -c "
SELECT 
    schemaname,
    tablename,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_live_tup,
    n_dead_tup
FROM pg_stat_user_tables 
ORDER BY n_live_tup DESC;
"

# Monitor cache hit rates
curl -s http://localhost:8000/cache/stats | jq
```

## Backup and Recovery

### Automated Backups

```bash
# Daily backup (add to cron)
0 2 * * * /path/to/scripts/deploy.sh prod backup

# Weekly backup with retention
0 3 * * 0 /path/to/scripts/backup-weekly.sh
```

### Manual Backup

```bash
# Create backup
./scripts/deploy.sh prod backup

# List backups
ls -la backups/

# Restore from backup
docker exec -i tv-postgres-prod psql -U stocksblitz stocksblitz_unified < backups/backup_prod_20241023_120000.sql
```

## Scaling

### Horizontal Scaling

Add more backend instances:

```yaml
# In docker-compose.prod.yml
backend2:
  image: ghcr.io/yourorg/tradingview-ml-viz-backend:latest
  container_name: tv-backend-prod-2
  # ... same config as backend
  
backend3:
  image: ghcr.io/yourorg/tradingview-ml-viz-backend:latest
  container_name: tv-backend-prod-3
  # ... same config as backend
```

Update nginx load balancer:

```nginx
upstream backend_servers {
    least_conn;
    server backend:8000 max_fails=3 fail_timeout=30s;
    server backend2:8000 max_fails=3 fail_timeout=30s;
    server backend3:8000 max_fails=3 fail_timeout=30s;
    keepalive 32;
}
```

### Database Scaling

1. **Read Replicas:**
   ```bash
   # Set up TimescaleDB read replica
   docker run -d \
     --name tv-postgres-read-replica \
     -e POSTGRES_USER=stocksblitz \
     -e POSTGRES_PASSWORD=$DB_PASSWORD \
     timescale/timescaledb:latest-pg15
   ```

2. **Connection Pooling:**
   ```bash
   # Use PgBouncer for connection pooling
   docker run -d \
     --name pgbouncer \
     -e DATABASES_HOST=postgres \
     -e DATABASES_PORT=5432 \
     -e DATABASES_USER=stocksblitz \
     -e DATABASES_PASSWORD=$DB_PASSWORD \
     pgbouncer/pgbouncer:latest
   ```

## Security

### SSL/TLS Configuration

1. **Certificate Management:**
   ```bash
   # Auto-renewal with Let's Encrypt
   certbot certonly --webroot -w /var/www/html -d yourdomain.com
   ```

2. **Security Headers:**
   - Content Security Policy
   - HSTS
   - X-Frame-Options
   - X-Content-Type-Options

### Access Control

1. **Network Security:**
   ```bash
   # Firewall rules
   ufw allow 22    # SSH
   ufw allow 80    # HTTP
   ufw allow 443   # HTTPS
   ufw deny 5432   # Database (internal only)
   ufw deny 6379   # Redis (internal only)
   ```

2. **Rate Limiting:**
   - API: 60 requests/minute per IP
   - General: 1 request/second per IP

## Troubleshooting

### Common Issues

1. **Service Won't Start:**
   ```bash
   # Check logs
   ./scripts/deploy.sh prod logs backend
   
   # Check resource usage
   docker stats
   
   # Check disk space
   df -h
   ```

2. **Database Connection Issues:**
   ```bash
   # Test database connection
   docker exec tv-postgres-prod pg_isready -U stocksblitz
   
   # Check database logs
   docker logs tv-postgres-prod
   ```

3. **High Memory Usage:**
   ```bash
   # Restart services
   ./scripts/deploy.sh prod restart
   
   # Check memory leaks
   docker exec tv-backend-prod ps aux --sort=-%mem
   ```

### Emergency Procedures

1. **Rollback Deployment:**
   ```bash
   # Stop current version
   ./scripts/deploy.sh prod stop
   
   # Deploy previous version
   docker-compose -f deployment/docker/docker-compose.prod.yml pull
   ./scripts/deploy.sh prod start
   ```

2. **Database Recovery:**
   ```bash
   # Stop services
   ./scripts/deploy.sh prod stop
   
   # Restore from backup
   docker exec -i tv-postgres-prod psql -U stocksblitz stocksblitz_unified < backups/latest-backup.sql
   
   # Restart services
   ./scripts/deploy.sh prod start
   ```

## Support

For deployment issues:
1. Check this documentation
2. Review logs: `./scripts/deploy.sh [env] logs`
3. Check health: `./scripts/deploy.sh [env] health`
4. Contact the development team