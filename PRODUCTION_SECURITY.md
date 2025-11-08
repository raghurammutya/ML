# Production Environment Security Guide

This document outlines the security measures implemented to protect the TradingView ML Visualization production environment from unauthorized changes.

## 🔒 Security Features Implemented

### 1. Production Environment Lock
- **File Protection**: Critical files are set to read-only
- **Directory Protection**: Key directories have write protection
- **Lock File**: Creates a system-wide lock indicator
- **Integrity Checksums**: SHA256 checksums for all critical files

### 2. Deployment Controls
- **Secure Deployment**: Only authorized deployments allowed
- **Pre-deployment Validation**: Automatic checks before deployment
- **Rollback Capability**: Automatic backup and restore on failure
- **Health Verification**: Post-deployment health checks

### 3. Continuous Monitoring
- **File Integrity Monitoring**: Real-time detection of unauthorized changes
- **Lock Validation**: Ensures production lock remains intact
- **Security Alerts**: Automated alerts for security violations
- **System Service**: Background monitoring service

### 4. Git Protection
- **Pre-commit Hooks**: Prevents commits to production branches when locked
- **Syntax Validation**: Validates code before commits
- **Branch Protection**: Safeguards against direct production changes

## 📁 Protected Files and Directories

### Critical Configuration Files
- `.env.prod` - Production environment variables
- `docker-compose.unified.yml` - Docker services configuration
- `deployment/nginx.conf.template` - Nginx configuration
- `deployment/Dockerfile.frontend.unified` - Frontend Docker build
- `backend/Dockerfile` - Backend Docker build
- `backend/requirements.txt` - Python dependencies

### Application Code
- `backend/app/config.py` - Application configuration
- `backend/app/database.py` - Database connections
- `backend/app/main.py` - Main application entry
- `frontend/src/App.tsx` - Main React component
- `frontend/src/components/CustomChartWithMLLabels.tsx` - Chart component
- `frontend/package.json` - Node.js dependencies

### Critical Directories
- `backend/app/` - Backend application code
- `frontend/src/` - Frontend source code
- `deployment/` - Deployment configurations
- `scripts/` - Management scripts

## 🛠️ Management Scripts

### 1. Lock Production Environment
```bash
sudo ./scripts/lock-production.sh
```
**What it does:**
- Creates production lock file
- Sets files to read-only
- Generates integrity checksums
- Creates backup
- Sets up monitoring scripts

### 2. Validate Production Deployment
```bash
./scripts/validate-deployment.sh
```
**What it does:**
- Validates production lock
- Checks file integrity
- Verifies environment variables
- Checks Docker services

### 3. Secure Deployment
```bash
./scripts/secure-deploy.sh <environment>
```
**Options:**
- `development` - Deploy to dev environment
- `production` - Deploy to production (requires unlock)

**Features:**
- Pre-deployment validation
- Automatic backup creation
- Health verification
- Automatic rollback on failure

### 4. Production Monitoring
```bash
./scripts/monitor-production.sh [--daemon]
```
**Modes:**
- Without `--daemon`: One-time integrity check
- With `--daemon`: Continuous monitoring (every 5 minutes)

### 5. Emergency Unlock
```bash
sudo ./scripts/unlock-production.sh
```
**⚠️ Use only for authorized maintenance**
- Requires root privileges
- Logs all unlock activities
- Prompts for reason and maintainer ID
- Restores original file permissions

### 6. Setup Monitoring Service
```bash
sudo ./scripts/setup-monitoring-service.sh
```
**Creates systemd service for:**
- Continuous background monitoring
- Automatic restart on failure
- Centralized logging
- Log rotation

## 🔧 Usage Workflow

### Normal Operations (Production Locked)
1. Production environment is locked by default
2. Development continues in feature branches
3. Background monitoring runs continuously
4. No direct changes to production files possible

### Authorized Deployment Process
1. **Prepare Changes**: Develop and test in development environment
   ```bash
   ./scripts/secure-deploy.sh development
   ```

2. **Unlock Production**: For authorized maintenance only
   ```bash
   sudo ./scripts/unlock-production.sh
   ```

3. **Deploy to Production**: With automatic validation and rollback
   ```bash
   ./scripts/secure-deploy.sh production
   ```

4. **Re-lock Production**: After successful deployment
   ```bash
   sudo ./scripts/lock-production.sh
   ```

### Monitoring and Alerts

#### Start Monitoring Service
```bash
sudo systemctl start tradingview-monitor
sudo systemctl enable tradingview-monitor
```

#### Check Monitoring Status
```bash
sudo systemctl status tradingview-monitor
```

#### View Real-time Logs
```bash
sudo journalctl -u tradingview-monitor -f
```

#### Check Security Alerts
```bash
sudo tail -f /var/log/tradingview-security-alerts.log
```

## 🚨 Security Incident Response

### If Unauthorized Changes Detected
1. **Immediate Response**:
   - Check security alert logs
   - Identify what changed
   - Determine if malicious or accidental

2. **Investigation**:
   ```bash
   # Check what files changed
   sha256sum -c .production_checksums
   
   # View recent system activity
   sudo journalctl -u tradingview-monitor --since "1 hour ago"
   
   # Check who has been accessing the system
   sudo last -n 20
   ```

3. **Recovery**:
   - If changes are unauthorized, restore from backup
   - If changes are legitimate, regenerate checksums
   - Re-lock environment

### If Production Lock is Tampered
1. **Check lock file status**:
   ```bash
   ls -la /tmp/tradingview-production.lock
   cat /tmp/tradingview-production.lock
   ```

2. **Restore protection**:
   ```bash
   sudo ./scripts/lock-production.sh
   ```

3. **Investigate access logs**:
   ```bash
   sudo grep "tradingview" /var/log/auth.log
   ```

## 📊 Log Files and Monitoring

### Log Locations
- **Protection Events**: `/var/log/tradingview-protection.log`
- **Security Alerts**: `/var/log/tradingview-security-alerts.log`
- **Deployments**: `/var/log/tradingview-deployments.log`
- **Maintenance**: `/var/log/tradingview-maintenance.log`
- **Service Logs**: `sudo journalctl -u tradingview-monitor`

### Backup Locations
- **System Backups**: `/opt/tradingview-backups/`
- **Retention**: Last 10 backups automatically kept
- **Backup Types**: 
  - Pre-lock backups
  - Pre-deployment backups
  - Emergency backups

## ⚡ Quick Reference Commands

### Emergency Commands
```bash
# Emergency unlock (requires sudo)
sudo ./scripts/unlock-production.sh

# Force deployment (bypass lock)
./scripts/secure-deploy.sh production --force

# Check production status
./scripts/validate-deployment.sh

# View active alerts
sudo tail /var/log/tradingview-security-alerts.log
```

### Daily Operations
```bash
# Deploy to development
./scripts/secure-deploy.sh development

# Check monitoring status
sudo systemctl status tradingview-monitor

# View recent logs
sudo journalctl -u tradingview-monitor --since today
```

### Maintenance Mode
```bash
# 1. Unlock for maintenance
sudo ./scripts/unlock-production.sh

# 2. Make authorized changes
# ... perform maintenance ...

# 3. Deploy changes
./scripts/secure-deploy.sh production

# 4. Re-lock environment
sudo ./scripts/lock-production.sh
```

## 🔐 Security Best Practices

1. **Never bypass the lock system** unless absolutely necessary
2. **Always use the secure deployment script** for production changes
3. **Monitor security logs regularly** for suspicious activity
4. **Keep backups** before making any significant changes
5. **Document all maintenance activities** in the maintenance log
6. **Use feature branches** for development, never commit directly to master when locked
7. **Regularly verify integrity** using the validation script
8. **Set up monitoring alerts** for real-time security notifications

## 🚀 Integration with CI/CD

To integrate with CI/CD pipelines, ensure:

1. **Pre-deployment validation** in CI pipeline:
   ```bash
   # In CI script
   ./scripts/validate-deployment.sh
   ```

2. **Use secure deployment** for automated deployments:
   ```bash
   # In CD script
   ./scripts/secure-deploy.sh production
   ```

3. **Monitor deployment health** in pipeline:
   ```bash
   # Health check in pipeline
   curl -f http://localhost:8888/health
   ```

---

**Remember**: This security system is designed to prevent accidental or unauthorized changes to production. In case of emergencies, the unlock mechanism provides authorized access while maintaining full audit trails.