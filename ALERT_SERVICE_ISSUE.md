# Alert Service - Critical Issue Report

**Status**: 🔴 SERVICE DOWN
**Priority**: CRITICAL
**Assigned To**: Alert Service Team
**Date**: November 4, 2025

---

## Issue Summary

Alert service fails to start due to port conflict on port 8003.

**Exit Code**: 128
**Error Message**:
```
failed to set up container networking: driver failed programming external connectivity
on endpoint tv-alert (cb050ccd8592e58389ee0795c2efbc860b282a96db9511de22e30a3e5a0386e9):
Bind for 0.0.0.0:8003 failed: port is already allocated
```

---

## Impact

| Aspect | Impact Level | Details |
|--------|-------------|---------|
| **Service Status** | 🔴 CRITICAL | Service cannot start |
| **User Impact** | 🔴 CRITICAL | No alert functionality available |
| **Affected Features** | 🔴 CRITICAL | - Price alerts<br>- Threshold notifications<br>- Custom user alerts |
| **Business Impact** | 🔴 HIGH | Users cannot receive trading alerts |

---

## Root Cause

Port 8003 is already in use by another process, preventing Docker from binding the alert service to this port. This typically occurs when:
1. A previous alert service container was not properly cleaned up
2. Another service is using port 8003
3. A zombie process is holding the port

---

## How to Reproduce

```bash
# Check service status
docker ps -a | grep alert

# View error details
docker inspect tv-alert --format='{{.State.Status}} | Exit Code: {{.State.ExitCode}} | Error: {{.State.Error}}'

# Expected output:
# created | Exit Code: 128 | Error: failed to set up container networking...
```

---

## Required Fix

Follow these steps in order:

### Step 1: Identify What's Using Port 8003

```bash
# Check if port is in use
lsof -i :8003

# Alternative command
netstat -tulpn | grep 8003

# Check for Docker containers using this port
docker ps -a | grep 8003
```

**Possible outputs**:
- **Old container**: Previous alert service container not cleaned up
- **Other process**: Another application using port 8003
- **No output**: Port may be in TIME_WAIT state

---

### Step 2: Choose Resolution Strategy

#### Option A: Clean Up Old Alert Service Container (RECOMMENDED)

```bash
# 1. List all alert service containers
docker ps -a | grep alert

# 2. Stop old containers
docker stop $(docker ps -a | grep alert | awk '{print $1}')

# 3. Remove old containers
docker rm -f $(docker ps -a | grep alert | awk '{print $1}')

# 4. Verify port is free
lsof -i :8003
# Should return empty (no output)

# 5. Start alert service
docker-compose up -d alert_service

# 6. Verify startup
docker logs tv-alert --tail 50 --follow
```

---

#### Option B: Kill Process Using Port 8003 (If Not Docker)

**⚠️ WARNING**: Only do this if you know it's safe to kill the process.

```bash
# 1. Find process ID using port 8003
lsof -i :8003 | grep LISTEN
# Example output: python3  12345 user    3u  IPv4 0x1234  0t0  TCP *:8003 (LISTEN)

# 2. Check what the process is
ps aux | grep 12345

# 3. If safe to kill, stop the process
kill 12345

# 4. If process doesn't stop, force kill
kill -9 12345

# 5. Verify port is free
lsof -i :8003

# 6. Start alert service
docker-compose up -d alert_service
```

---

#### Option C: Reassign Alert Service to Different Port

**Use this option if port 8003 is needed by another critical service.**

```bash
# 1. Edit docker-compose.yml
cd /home/stocksadmin/Quantagro/tradingview-viz
nano docker-compose.yml

# 2. Find alert_service section and change port mapping
# BEFORE:
# alert_service:
#   ports:
#     - "8003:8003"

# AFTER:
# alert_service:
#   ports:
#     - "8004:8003"  # External port 8004, internal port 8003

# 3. Save and exit (Ctrl+X, Y, Enter)

# 4. Remove old container
docker-compose rm -f alert_service

# 5. Start with new configuration
docker-compose up -d alert_service

# 6. Verify on new port
curl http://localhost:8004/health  # Note: port 8004 now
```

**⚠️ IMPORTANT**: If you change the port, update:
- Frontend configuration (if it calls alert service directly)
- Any other services that depend on alert service
- Documentation and environment files

---

### Step 3: Verify Fix

```bash
# 1. Check container status
docker ps | grep alert
# Expected: Should show "Up" status with port 8003->8003 (or 8004->8003)

# 2. Check logs for successful startup
docker logs tv-alert --tail 50
# Expected: No error messages, should see startup confirmation

# 3. Test health endpoint
curl -s http://localhost:8003/health | jq '.'
# Expected: {"status": "ok", ...}

# 4. Test alert creation (if applicable)
curl -X POST http://localhost:8003/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "NIFTY50",
    "condition": "above",
    "value": 24000,
    "user_id": "test_user"
  }'
# Expected: Alert created successfully
```

---

## Success Criteria

- [ ] Port 8003 is no longer in use by conflicting process
- [ ] Alert service container starts successfully
- [ ] Container status shows "Up" (not "Exited" or "Created")
- [ ] Health endpoint responds with HTTP 200
- [ ] Alert creation API works correctly
- [ ] No port binding errors in logs

---

## Troubleshooting

### Issue: Port Still Shows as In Use After Cleanup

```bash
# Wait for port to be released (TIME_WAIT state)
sleep 10

# Check port status
netstat -an | grep 8003

# If still in TIME_WAIT, wait 30-60 seconds and try again
```

### Issue: Docker Service Won't Start After Port Cleanup

```bash
# Restart Docker daemon
sudo systemctl restart docker

# Wait for Docker to restart
sleep 5

# Try starting alert service again
docker-compose up -d alert_service
```

### Issue: Permission Denied When Killing Process

```bash
# Use sudo (if safe and you have permissions)
sudo lsof -i :8003
sudo kill -9 <PID>

# Then start alert service
docker-compose up -d alert_service
```

---

## Configuration Reference

**Files to Check**:
1. `/home/stocksadmin/Quantagro/tradingview-viz/docker-compose.yml`
2. `/home/stocksadmin/Quantagro/tradingview-viz/alert_service/.env`

**Relevant Configuration**:
```yaml
# docker-compose.yml
alert_service:
  build: ./alert_service
  ports:
    - "8003:8003"  # External:Internal port mapping
  environment:
    - ALERT_SERVICE_PORT=8003
    - DATABASE_URL=postgresql://...
    - REDIS_URL=redis://...
```

---

## Prevention for Future

To prevent this issue from recurring:

1. **Always use docker-compose down** instead of manually stopping containers:
   ```bash
   # Good practice:
   docker-compose down alert_service

   # Avoid:
   docker stop tv-alert
   ```

2. **Clean up before starting**:
   ```bash
   # Before deployment, clean up old containers:
   docker-compose down
   docker-compose up -d
   ```

3. **Add cleanup script** (optional):
   ```bash
   # Create scripts/cleanup_alert_service.sh
   #!/bin/bash
   docker stop tv-alert 2>/dev/null
   docker rm -f tv-alert 2>/dev/null
   docker-compose up -d alert_service
   ```

4. **Use health checks in docker-compose.yml**:
   ```yaml
   alert_service:
     healthcheck:
       test: ["CMD", "curl", "-f", "http://localhost:8003/health"]
       interval: 30s
       timeout: 10s
       retries: 3
   ```

---

## Time Estimate

- **Option A (Clean up Docker containers)**: 5-10 minutes
- **Option B (Kill conflicting process)**: 10-15 minutes
- **Option C (Reassign port)**: 15-20 minutes

---

## Additional Diagnostics

If the issue persists after trying all options:

```bash
# 1. Check Docker networking
docker network ls
docker network inspect tradingview-viz_default

# 2. Check if port is bound to specific IP
netstat -an | grep 8003 | grep LISTEN

# 3. Check iptables rules (if applicable)
sudo iptables -L -n | grep 8003

# 4. Check Docker daemon logs
sudo journalctl -u docker --since "10 minutes ago" | grep 8003

# 5. Try stopping all Docker services and restart
docker-compose down
docker system prune -f
docker-compose up -d
```

---

## Contact

**Reported By**: Backend Release Team
**Blocking**: Backend production release
**Urgency**: IMMEDIATE - Alert functionality unavailable

**Questions?** Check the full assessment: `/mnt/stocksblitz-data/Quantagro/tradingview-viz/PRODUCTION_READINESS_ASSESSMENT.md`

---

## Status Tracking

- [ ] Issue acknowledged by alert service team
- [ ] Port conflict identified (Step 1 completed)
- [ ] Resolution strategy selected (Option A/B/C)
- [ ] Conflicting process stopped/port freed
- [ ] Alert service restarted
- [ ] Verification tests passed
- [ ] Issue resolved and closed

**Last Updated**: November 4, 2025
