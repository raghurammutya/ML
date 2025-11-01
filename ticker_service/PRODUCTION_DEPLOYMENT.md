# Production Deployment Guide

## Pre-Deployment Checklist

### Security ✅

- [ ] Generate strong API key (32+ bytes): `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
- [ ] Store all secrets in secrets manager (NOT .env files)
- [ ] Set `ENVIRONMENT=production` in production environment
- [ ] Verify `API_KEY_ENABLED=true`
- [ ] Change all default passwords (database, Redis)
- [ ] Enable HTTPS/TLS on all endpoints
- [ ] Configure firewall rules
- [ ] Review and restrict database permissions
- [ ] Set up audit logging
- [ ] Test backup and recovery procedures

### Infrastructure ✅

- [ ] PostgreSQL/TimescaleDB instance provisioned and accessible
- [ ] Redis instance provisioned and accessible
- [ ] Log aggregation system configured (ELK, CloudWatch, etc.)
- [ ] Metrics collection configured (Prometheus, Datadog, etc.)
- [ ] Alert rules configured (PagerDuty, Opsgenie, etc.)
- [ ] Load balancer configured with health checks
- [ ] Auto-scaling policies defined
- [ ] Backup schedule configured

### Testing ✅

- [ ] All tests pass: `pytest`
- [ ] Code coverage ≥ 70%: `pytest --cov=app --cov-fail-under=70`
- [ ] Load tests completed successfully
- [ ] Security scan completed (no critical vulnerabilities)
- [ ] Integration tests pass against staging environment

## Deployment Methods

### Method 1: Docker Compose (Simple)

**Best for**: Small deployments, single server

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  ticker-service:
    image: ticker-service:latest
    restart: unless-stopped
    environment:
      ENVIRONMENT: production
      API_KEY: ${API_KEY}  # From host environment
      REDIS_URL: ${REDIS_URL}
      INSTRUMENT_DB_HOST: ${DB_HOST}
      INSTRUMENT_DB_PASSWORD: ${DB_PASSWORD}
      LOG_DIR: /app/logs
    volumes:
      - ./logs:/app/logs
      - ./tokens:/app/tokens:ro  # Read-only token files
    ports:
      - "8080:8080"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

**Deploy:**
```bash
# Build image
docker build -t ticker-service:latest .

# Deploy
docker-compose -f docker-compose.prod.yml up -d

# Check status
docker-compose -f docker-compose.prod.yml ps
docker-compose -f docker-compose.prod.yml logs -f ticker-service
```

### Method 2: Kubernetes (Recommended for Production)

**Best for**: Scalable, high-availability deployments

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ticker-service
  labels:
    app: ticker-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ticker-service
  template:
    metadata:
      labels:
        app: ticker-service
    spec:
      serviceAccountName: ticker-service
      securityContext:
        runAsUser: 1000
        runAsNonRoot: true
        fsGroup: 1000
      containers:
      - name: ticker-service
        image: your-registry.com/ticker-service:v1.0.0
        imagePullPolicy: Always
        ports:
        - containerPort: 8080
          name: http
        env:
        - name: ENVIRONMENT
          value: "production"
        - name: API_KEY
          valueFrom:
            secretKeyRef:
              name: ticker-service-secrets
              key: api-key
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: ticker-service-secrets
              key: redis-url
        - name: INSTRUMENT_DB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: ticker-service-secrets
              key: db-password
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 40
          periodSeconds: 30
          timeoutSeconds: 10
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 20
          periodSeconds: 10
          timeoutSeconds: 5
        volumeMounts:
        - name: logs
          mountPath: /app/logs
      volumes:
      - name: logs
        emptyDir: {}

---
apiVersion: v1
kind: Service
metadata:
  name: ticker-service
spec:
  selector:
    app: ticker-service
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8080
  type: LoadBalancer

---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: ticker-service-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: ticker-service
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

**Deploy to Kubernetes:**
```bash
# Create secrets
kubectl create secret generic ticker-service-secrets \
  --from-literal=api-key="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  --from-literal=redis-url="redis://:password@redis:6379/0" \
  --from-literal=db-password="your-db-password"

# Apply configuration
kubectl apply -f k8s/

# Check deployment
kubectl get pods -l app=ticker-service
kubectl logs -f deployment/ticker-service
```

### Method 3: AWS ECS/Fargate

```json
{
  "family": "ticker-service",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "containerDefinitions": [
    {
      "name": "ticker-service",
      "image": "your-ecr-repo/ticker-service:latest",
      "portMappings": [
        {
          "containerPort": 8080,
          "protocol": "tcp"
        }
      ],
      "secrets": [
        {
          "name": "API_KEY",
          "valueFrom": "arn:aws:secretsmanager:region:account:secret:ticker-service/api-key"
        },
        {
          "name": "REDIS_URL",
          "valueFrom": "arn:aws:secretsmanager:region:account:secret:ticker-service/redis-url"
        }
      ],
      "environment": [
        {
          "name": "ENVIRONMENT",
          "value": "production"
        }
      ],
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"],
        "interval": 30,
        "timeout": 10,
        "retries": 3,
        "startPeriod": 40
      },
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/ticker-service",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

## Post-Deployment Verification

### 1. Health Check

```bash
curl https://your-domain.com/health
```

Expected response:
```json
{
  "status": "ok",
  "environment": "production",
  "ticker": {
    "running": true
  },
  "dependencies": {
    "redis": "ok",
    "database": "ok",
    "instrument_registry": {
      "status": "ok",
      "cached_instruments": 5000
    }
  }
}
```

### 2. Metrics Endpoint

```bash
curl https://your-domain.com/metrics
```

Should return Prometheus metrics.

### 3. Authentication Test

```bash
# Should fail without API key
curl https://your-domain.com/advanced/batch-orders

# Should succeed with API key
curl -H "X-API-Key: your-api-key" \
  https://your-domain.com/advanced/batch-orders
```

### 4. Load Test

```bash
# Using Apache Bench
ab -n 1000 -c 10 https://your-domain.com/health

# Using k6
k6 run load-test.js
```

## Monitoring

### Key Metrics to Monitor

1. **Application Metrics** (Prometheus)
   - Request rate (`/metrics`)
   - Error rate
   - Response time (p50, p95, p99)
   - Active subscriptions count
   - WebSocket connection count

2. **System Metrics**
   - CPU usage (target: < 70%)
   - Memory usage (target: < 80%)
   - Disk usage (logs directory)
   - Network I/O

3. **Business Metrics**
   - Order success rate (target: > 99%)
   - Batch order completion time
   - Webhook delivery rate
   - API rate limit hits

### Alerts

Configure alerts for:

```yaml
# alerts.yaml
groups:
- name: ticker_service
  rules:
  - alert: HighErrorRate
    expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
    for: 5m
    annotations:
      summary: "High error rate detected"

  - alert: ServiceDown
    expr: up{job="ticker-service"} == 0
    for: 1m
    annotations:
      summary: "Ticker service is down"

  - alert: HighMemoryUsage
    expr: container_memory_usage_bytes / container_spec_memory_limit_bytes > 0.85
    for: 5m
    annotations:
      summary: "High memory usage"

  - alert: DatabaseConnectionFailed
    expr: ticker_service_db_connection_errors_total > 10
    for: 5m
    annotations:
      summary: "Database connection issues"
```

## Logging

### Log Aggregation

**ELK Stack:**
```yaml
# filebeat.yml
filebeat.inputs:
- type: container
  paths:
    - '/var/lib/docker/containers/*/*.log'
  processors:
  - add_docker_metadata:
  - drop_event:
      when:
        not:
          equals:
            docker.container.labels.app: "ticker-service"

output.elasticsearch:
  hosts: ["elasticsearch:9200"]
```

**CloudWatch (AWS):**
```python
# Already configured in ECS task definition
# Logs automatically sent to CloudWatch Logs
```

### Log Queries

```bash
# Find all errors in last hour
logs filter "ERROR" | last 1h

# Find authentication failures
logs filter "Invalid API key" | count

# Find slow requests
logs filter "took" | filter duration > 1000
```

## Rollback Procedure

### Quick Rollback

**Docker Compose:**
```bash
# Rollback to previous version
docker-compose -f docker-compose.prod.yml down
docker pull ticker-service:v1.0.0  # Previous version
docker-compose -f docker-compose.prod.yml up -d
```

**Kubernetes:**
```bash
# Rollback deployment
kubectl rollout undo deployment/ticker-service

# Or rollback to specific revision
kubectl rollout undo deployment/ticker-service --to-revision=2
```

**ECS:**
```bash
aws ecs update-service \
  --cluster production \
  --service ticker-service \
  --task-definition ticker-service:previous-revision
```

### Estimated Rollback Time

- Docker Compose: 2-5 minutes
- Kubernetes: 2-3 minutes (with rolling update)
- ECS/Fargate: 3-5 minutes

## Disaster Recovery

### Backup Strategy

1. **Database Backups**
   - Frequency: Every 6 hours
   - Retention: 30 days
   - Type: Full + incremental
   - Encryption: AES-256

2. **Configuration Backups**
   - Frequency: On every change
   - Location: Git repository + encrypted S3
   - Include: Kubernetes manifests, env files

3. **Token Files**
   - Frequency: Daily
   - Location: Encrypted S3 bucket
   - Access: Restricted to ops team

### Recovery Procedures

**Database Corruption:**
```bash
# 1. Stop service
kubectl scale deployment/ticker-service --replicas=0

# 2. Restore database from backup
pg_restore -d stocksblitz_unified backup.dump

# 3. Verify data integrity
psql -c "SELECT COUNT(*) FROM instrument_subscriptions"

# 4. Restart service
kubectl scale deployment/ticker-service --replicas=3
```

**Complete System Failure:**
1. Provision new infrastructure (Terraform/CloudFormation)
2. Restore database from latest backup
3. Deploy application from last known good version
4. Restore token files from encrypted backup
5. Verify all health checks pass
6. Update DNS to point to new infrastructure

**RTO (Recovery Time Objective)**: 30 minutes
**RPO (Recovery Point Objective)**: 6 hours

## Scaling Guidelines

### Vertical Scaling

Increase resources when:
- CPU usage > 70% sustained
- Memory usage > 80% sustained
- Response time p99 > 1000ms

```bash
# Kubernetes
kubectl set resources deployment ticker-service \
  -c ticker-service \
  --limits=cpu=4,memory=4Gi \
  --requests=cpu=2,memory=2Gi
```

### Horizontal Scaling

Add replicas when:
- Request rate > 1000 req/sec per instance
- WebSocket connections > 8000 per instance
- Queue depth increasing

```bash
# Kubernetes
kubectl scale deployment ticker-service --replicas=5
```

### Database Scaling

- Read replicas for historical queries
- Connection pooling (already configured)
- Index optimization for subscription queries

## Troubleshooting

### Common Issues

**1. Service Won't Start**
```bash
# Check logs
kubectl logs deployment/ticker-service

# Common causes:
# - Missing API_KEY in production
# - Database connection failure
# - Invalid environment variables
```

**2. High Memory Usage**
```bash
# Check log file size
docker exec ticker-service ls -lh /app/logs

# Solution: Logs rotate automatically at 100MB
```

**3. Instrument Registry Not Loading**
```bash
# Check health endpoint
curl https://your-domain.com/health

# Force refresh
curl -X POST https://your-domain.com/admin/instrument-refresh?force=true
```

**4. Authentication Failures**
```bash
# Verify API key is set
kubectl get secret ticker-service-secrets -o jsonpath='{.data.api-key}' | base64 -d

# Check environment variable
kubectl exec deployment/ticker-service -- env | grep API_KEY
```

## Support

- **Documentation**: https://github.com/your-org/ticker-service
- **Runbooks**: `/docs/runbooks/`
- **On-call**: PagerDuty escalation policy
- **Slack**: #ticker-service-prod
