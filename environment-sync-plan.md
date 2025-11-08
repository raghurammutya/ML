# Complete Environment Synchronization Plan

## Current State Summary
- **Production**: ✅ Stable, protected, running current code
- **Development**: ⚠️ Functional but frontend has timezone differences
- **GitHub**: ❌ Missing recent improvements and security features

## Phase 1: Prepare for Synchronization

### Step 1.1: Create Safe Backup
```bash
# Backup current state before any changes
git stash push -m "Current development work - pre-sync backup"
git tag backup-pre-sync-$(date +%Y%m%d-%H%M%S)
```

### Step 1.2: Document Current Changes
```bash
# Create detailed change log
git diff HEAD > current-changes.patch
git status --porcelain > current-status.txt
```

## Phase 2: GitHub Repository Sync

### Step 2.1: Commit Development Improvements
```bash
# Commit the backend improvements (keeping dev database config separate)
git add backend/app/routes/marks_asyncpg.py
git commit -m "Add debug logging to marks API for better monitoring"

# Commit security and backup systems
git add scripts/
git add .github/workflows/
git add database-backup.sh
git add scripts/lock-production.sh
git add scripts/monitor-production.sh
git commit -m "Add production security, backup automation, and CI/CD pipeline"
```

### Step 2.2: Create Environment-Specific Configuration
```bash
# Keep environment configs separate
git add .env.dev
git commit -m "Add development environment configuration"
# Note: .env.prod should remain protected and not in git
```

## Phase 3: Frontend Code Synchronization

### Step 3.1: Temporary Security Unlock (Critical Step)
```bash
# IMPORTANT: This temporarily unlocks production files
./scripts/unlock-production.sh
```

### Step 3.2: Sync Frontend Code
```bash
# Copy production frontend code to main location
cp -r tradingview-ml-viz-production/frontend/src/* frontend/src/

# Update timezone handling to UTC (production standard)
# This fixes the timezone display issue in development
```

### Step 3.3: Commit Frontend Sync
```bash
git add frontend/src/
git commit -m "Sync frontend code - fix timezone display to use UTC"
```

### Step 3.4: Re-lock Production
```bash
# IMPORTANT: Re-enable protection immediately
./scripts/lock-production.sh
```

## Phase 4: Rebuild Development Environment

### Step 4.1: Rebuild with Synced Code
```bash
# Rebuild development containers with updated code
docker-compose -f docker-compose.unified.yml --env-file .env.dev build
docker-compose -f docker-compose.unified.yml --env-file .env.dev up -d
```

### Step 4.2: Verify Development Environment
```bash
# Test all functionality
./check-dev-environment.sh
curl -s http://localhost:8001/health
curl -s http://localhost:3001/tradingview-api/health
```

## Phase 5: Production Validation

### Step 5.1: Verify Production Unchanged
```bash
# Ensure production is still running correctly
curl -s http://localhost:8888/health
curl -s http://localhost:3080/health
./scripts/monitor-production.sh
```

### Step 5.2: Test Production Backup System
```bash
# Verify backup system is working
./database-backup.sh --test
```

## Phase 6: GitHub Repository Cleanup

### Step 6.1: Push All Changes
```bash
git push origin master
```

### Step 6.2: Create Development Branch
```bash
# Create proper development workflow
git checkout -b development
git push -u origin development
```

### Step 6.3: Update Documentation
```bash
# Add comprehensive README updates
git add README.md DEPLOYMENT.md
git commit -m "Update documentation for three-environment setup"
```

## Phase 7: Establish Ongoing Sync Process

### Step 7.1: Create Sync Scripts
```bash
# Create automated sync verification
./scripts/check-environment-sync.sh
```

### Step 7.2: Set Up Git Hooks
```bash
# Ensure any commits are properly tested
cp scripts/pre-commit-hook.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

## Risk Mitigation

### Critical Safety Measures:
1. **Production Backup**: Create full backup before any changes
2. **Gradual Rollout**: Test each phase in development first
3. **Rollback Plan**: Keep ability to quickly restore previous state
4. **Monitoring**: Continuous monitoring during sync process

### Emergency Rollback:
```bash
# If anything goes wrong
git checkout master
git reset --hard backup-pre-sync-YYYYMMDD-HHMMSS
./scripts/lock-production.sh  # Re-protect production
```

## Expected Timeline

| Phase | Duration | Risk Level |
|-------|----------|------------|
| Phase 1-2 (Git Sync) | 30 minutes | Low |
| Phase 3 (Frontend Sync) | 45 minutes | Medium |
| Phase 4 (Dev Rebuild) | 30 minutes | Low |
| Phase 5 (Prod Validation) | 15 minutes | Low |
| Phase 6-7 (Cleanup) | 30 minutes | Low |
| **Total** | **~3 hours** | **Medium** |

## Success Criteria

### ✅ All Environments Synced When:
- [ ] Development timezone matches production (UTC)
- [ ] All three environments have same codebase
- [ ] GitHub repository contains all improvements
- [ ] Production remains stable and protected
- [ ] Development fully functional for testing
- [ ] Backup and security systems operational
- [ ] CI/CD pipeline ready for future deployments

## Post-Sync Verification

### Final Tests:
1. **Production**: Charts load, timezone correct, labels work
2. **Development**: Charts load, timezone correct, labels work  
3. **GitHub**: All commits pushed, branches organized
4. **Security**: Production lock active, backups scheduled
5. **Monitoring**: All systems reporting healthy

Would you like me to proceed with this synchronization plan?