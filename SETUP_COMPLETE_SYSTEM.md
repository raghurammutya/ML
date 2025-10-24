# Complete System Setup Guide

## 🎯 Quick Setup Summary

Your TradingView ML Visualization system now includes comprehensive production security AND automated database backups. Here's how to activate everything:

## 🔒 Step 1: Activate Production Security

```bash
# Activate production environment lock
sudo ./scripts/lock-production.sh

# Setup continuous monitoring service
sudo ./scripts/setup-monitoring-service.sh
sudo systemctl start tradingview-monitor
```

## 💾 Step 2: Setup Database Backups

```bash
# Test database backup system
./database-backup.sh --test

# Setup hourly backup cron job
sudo ./setup-db-backup-cron.sh

# Test backup monitoring
./database-backup-monitor.sh --force-check
```

## 🚀 Step 3: Configure GitHub Actions (Optional)

1. **Add Repository Secrets** (Repository → Settings → Secrets):
   - `PRODUCTION_SERVER`: Your server IP (e.g., `5.223.52.98`)
   - `SSH_USER`: SSH username (e.g., `stocksadmin`)
   - `SSH_PRIVATE_KEY`: Your SSH private key
   - `DEV_SERVER`: Development server IP (optional)

2. **Generate SSH Keys**:
   ```bash
   ssh-keygen -t rsa -b 4096 -C "github-actions"
   # Copy private key to GitHub secrets
   # Add public key to server: ~/.ssh/authorized_keys
   ```

3. **Test Workflows**:
   - Push to `develop` branch → Automatic dev deployment
   - Use "Manual Production Deploy" → Safe production deployment

## 📊 System Overview

### 🔐 Production Security Features
- **File Protection**: Critical files set to read-only
- **Access Control**: Production lock prevents unauthorized changes  
- **Monitoring**: Real-time integrity checks and alerting
- **Git Protection**: Pre-commit hooks block direct production commits
- **Audit Trail**: Complete logging of all security events

### 💾 Database Backup Features
- **Hourly Backups**: Critical tables backed up every hour
- **Smart Rotation**: Keeps current + 1 previous backup
- **Integrity Checks**: Automated verification and monitoring
- **Easy Restoration**: Generated restoration scripts
- **Health Monitoring**: Alerts for backup failures or staleness

### 🚀 Deployment Features
- **Development Pipeline**: Automated testing and deployment
- **Production Safety**: Manual approval with comprehensive checks
- **Automatic Rollback**: Health verification with auto-recovery
- **Database Protection**: Pre-deployment backups
- **Environment Control**: Production lock integration

## 🛠️ Daily Operations

### Check System Status
```bash
# Production security status
./scripts/validate-deployment.sh

# Database backup status  
./database-backup.sh --status
./database-backup-monitor.sh --status

# Services status
sudo systemctl status tradingview-monitor
docker-compose -f docker-compose.unified.yml ps
```

### Development Workflow
```bash
# Work on features (safe, no restrictions)
git checkout develop
# Make changes
git commit -m "Add new feature"
git push origin develop  # Triggers auto-deployment to dev

# Create pull request to main
# → Triggers testing and validation
```

### Production Deployment Workflow

#### Option A: GitHub Actions (Recommended)
1. Go to GitHub Actions → "Manual Production Deploy"
2. Fill parameters:
   - Confirmation: `DEPLOY_TO_PRODUCTION`
   - Backup Database: ✅
   - Auto Rollback: ✅
3. Monitor deployment progress
4. Verify deployment success

#### Option B: Manual Server Deployment
```bash
# Unlock production
sudo ./scripts/unlock-production.sh

# Deploy safely
./scripts/secure-deploy.sh production

# Re-lock production
sudo ./scripts/lock-production.sh
```

## 📋 Monitoring & Alerts

### View Logs
```bash
# Security events
sudo tail -f /var/log/tradingview-security-alerts.log

# Database backups
sudo tail -f /var/log/tradingview-db-backup.log

# Backup alerts
sudo tail -f /var/log/tradingview-backup-alerts.log

# Deployments
sudo tail -f /var/log/tradingview-deployments.log

# Service monitoring
sudo journalctl -u tradingview-monitor -f
```

### Check Backup Health
```bash
# Current backup status
./database-backup-monitor.sh --status

# Recent alerts
./database-backup-monitor.sh --alerts

# List available backups
ls -la /opt/tradingview-db-backups/current/
ls -la /opt/tradingview-db-backups/previous/
```

## 🚨 Emergency Procedures

### Database Restoration
```bash
# List available backups
ls /opt/tradingview-db-backups/current/restore_*.sh

# Run restoration script
cd /opt/tradingview-db-backups/current
./restore_YYYYMMDD_HHMMSS.sh
```

### Production Rollback
```bash
# If deployment fails
sudo ./scripts/unlock-production.sh

# Restore from backup
latest_backup=$(ls -t /opt/tradingview-backups/pre_deploy_* | head -1)
sudo rsync -av --delete "$latest_backup/" /home/stocksadmin/Quantagro/tradingview-viz/

# Restart services
docker-compose -f docker-compose.unified.yml up -d

# Re-lock
sudo ./scripts/lock-production.sh
```

### Security Incident Response
```bash
# Check what changed
sha256sum -c .production_checksums

# View security events
sudo grep "SECURITY ALERT" /var/log/tradingview-security-alerts.log

# Restore protection
sudo ./scripts/lock-production.sh
```

## 🎛️ Configuration Files

### Critical Protected Files
- ✅ `.env.prod` - Production environment variables
- ✅ `docker-compose.unified.yml` - Service configuration  
- ✅ `frontend/src/App.tsx` - Main React component
- ✅ `frontend/src/components/CustomChartWithMLLabels.tsx` - Chart component
- ✅ `backend/app/main.py` - Backend application
- ✅ `deployment/nginx.conf.template` - Web server config

### Database Tables Backed Up
- ✅ `ml_labeled_data` - ML training labels
- ✅ `nifty50_ohlc` - NIFTY50 price data
- ✅ `nifty_fo_ohlc` - NIFTY futures/options data

### Backup Locations
- **Current**: `/opt/tradingview-db-backups/current/`
- **Previous**: `/opt/tradingview-db-backups/previous/`
- **Code Backups**: `/opt/tradingview-backups/`

## 🔧 Advanced Configuration

### Modify Backup Schedule
```bash
# Edit cron job
sudo -u stocksadmin crontab -e

# Current: Every hour at minute 0
# Change to every 30 minutes: */30 * * * *
```

### Add Monitoring Notifications
Edit monitoring scripts to add:
- Email notifications
- Slack webhooks  
- SMS alerts
- Custom monitoring integrations

### Customize Security Rules
```bash
# Edit security lock script
sudo nano ./scripts/lock-production.sh

# Add more protected files
# Modify file permissions
# Add custom integrity checks
```

## ✅ Verification Checklist

After setup, verify all systems:

### Security System
- [ ] `sudo ./scripts/lock-production.sh` - Activates protection
- [ ] `./scripts/validate-deployment.sh` - Passes all checks
- [ ] `sudo systemctl status tradingview-monitor` - Service running

### Backup System  
- [ ] `./database-backup.sh --test` - Connection successful
- [ ] `sudo -u stocksadmin crontab -l` - Cron job listed
- [ ] `./database-backup-monitor.sh --force-check` - Monitoring works

### Application
- [ ] Services running: `docker-compose ps`
- [ ] Frontend accessible: `http://server:3080`
- [ ] API responding: `http://server:8888/health`
- [ ] Charts loading with data

### GitHub Actions (if configured)
- [ ] Repository secrets configured
- [ ] SSH access working
- [ ] Development deployment tested
- [ ] Manual production workflow tested

---

## 🎉 Congratulations!

Your TradingView ML Visualization system is now:

🔒 **Fully Secured** - Protected against unauthorized changes  
💾 **Auto-Backed Up** - Critical data backed up hourly  
🚀 **CI/CD Ready** - Automated deployment pipelines  
📊 **Monitored** - Real-time health and security monitoring  
🛡️ **Resilient** - Automatic rollback and recovery  

**Your production environment is enterprise-ready!** 🚀