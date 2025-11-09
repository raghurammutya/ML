# Access Grafana & Prometheus from Windows

## ✅ Services are READY and Externally Accessible!

Your Prometheus and Grafana are now accessible from your Windows laptop.

---

## 🌐 Access URLs

Open these URLs in your Windows browser:

| Service | URL | Credentials |
|---------|-----|-------------|
| **Grafana** | **http://5.223.52.98:3000** | admin / admin |
| **Prometheus** | **http://5.223.52.98:9090** | No auth |

---

## 📋 Quick Start - Open in Windows Browser

### 1. Access Grafana Dashboard

1. **Open your browser** (Chrome, Edge, Firefox)
2. **Go to:** http://5.223.52.98:3000
3. **Login:**
   - Username: `admin`
   - Password: `admin`
4. **Change password** when prompted (first login)
5. **Navigate to Dashboard:**
   - Click hamburger menu (☰) on left
   - Click "Dashboards"
   - Open "Tick Processing - Performance & Health"

### 2. Access Prometheus

1. **Open your browser**
2. **Go to:** http://5.223.52.98:9090
3. **Check targets:** Click "Status" → "Targets" to see if ticker-service is being scraped

---

## ✅ Diagnostic Results

Both services are accessible:

```
✓ Grafana (5.223.52.98:3000): OK
✓ Prometheus (5.223.52.98:9090): OK
```

**Containers Running:**
- ticker-grafana: Up (Port 0.0.0.0:3000)
- ticker-prometheus: Up (Port 0.0.0.0:9090)

---

## 🔥 If You Need to Configure Firewall

⚠️ **You may need sudo access** to configure the firewall if connections are blocked.

### Check if Firewall is Blocking (from Windows)

Open PowerShell and try:

```powershell
# Test Grafana
Invoke-WebRequest -Uri "http://5.223.52.98:3000/api/health" -UseBasicParsing

# Test Prometheus
Invoke-WebRequest -Uri "http://5.223.52.98:9090/-/healthy" -UseBasicParsing
```

**If you get connection errors**, the firewall needs to be configured.

### Firewall Configuration Commands (requires sudo on server)

Ask the server admin to run these commands:

#### Option 1: UFW (Ubuntu)

```bash
sudo ufw allow 3000/tcp
sudo ufw allow 9090/tcp
sudo ufw reload
```

#### Option 2: firewalld (CentOS/RHEL)

```bash
sudo firewall-cmd --permanent --add-port=3000/tcp
sudo firewall-cmd --permanent --add-port=9090/tcp
sudo firewall-cmd --reload
```

#### Option 3: Cloud Security Groups

If on **AWS/Azure/GCP**, configure security groups to allow:
- Inbound TCP port 3000 (Grafana)
- Inbound TCP port 9090 (Prometheus)
- Source: Your IP or 0.0.0.0/0 (anywhere)

---

## 📊 What You'll See

### Grafana Dashboard Features

The "Tick Processing - Performance & Health" dashboard has **21 panels**:

#### Row 1: Overview
- Tick Throughput (ticks/sec)
- Active Accounts count
- Error Rate
- System Health indicator
- NIFTY underlying price

#### Row 2: Latency
- Tick Processing Latency (P50, P95, P99)
- Batch Flush Latency
- Greeks Calculation Latency

#### Row 3: Batching
- Batch Size Distribution
- Batches Flushed per Second
- Batch Fill Rate (%)
- Pending Batch Size

#### Row 4: Errors
- Validation Errors by Type
- Processing Errors by Type
- Error Distribution (Pie Chart)
- Total Errors Count

#### Row 5: Business Metrics
- Underlying Ticks Processed
- Option Ticks Processed
- Greeks Calculations/sec
- Market Depth Updates

### Prometheus Features

- **Metrics Browser:** Explore all available metrics
- **Targets:** See if ticker-service is being scraped
- **Alerts:** View active alerts (15 configured)
- **Graph:** Create custom queries and visualizations

---

## 🎯 Expected Behavior

### When Ticker Service is Running

You should see:
- ✅ Real-time metrics flowing
- ✅ All dashboard panels showing data
- ✅ ticker-service target UP in Prometheus
- ✅ Throughput graphs updating

### When Ticker Service is NOT Running

You'll see:
- ⚠️ Empty dashboard panels (no data)
- ⚠️ ticker-service target DOWN in Prometheus (red)
- ℹ️ This is normal - start ticker service to see metrics

**To start ticker service:**
```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/ticker_service
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## 🔧 Common Issues

### Issue 1: "This site can't be reached"

**Cause:** Firewall blocking ports

**Solution:**
1. Run diagnostic on server: `./monitoring/diagnose-connectivity.sh`
2. If external test fails but local passes → Firewall
3. Configure firewall (see commands above)

### Issue 2: Dashboard Shows "No Data"

**Cause:** Ticker service not running

**Solution:**
1. Check Prometheus targets: http://5.223.52.98:9090/targets
2. If ticker-service is DOWN → Start ticker service on port 8000
3. Wait 15 seconds for Prometheus to scrape
4. Refresh Grafana dashboard

### Issue 3: Can't Login to Grafana

**Default credentials:**
- Username: `admin`
- Password: `admin`

**If locked out:**
```bash
# Run on server
docker exec -it ticker-grafana grafana-cli admin reset-admin-password newpassword
```

---

## 📱 Bookmarks (Save These!)

Add these to your browser bookmarks:

1. **Grafana Dashboard**
   - URL: http://5.223.52.98:3000/dashboards

2. **Prometheus Targets**
   - URL: http://5.223.52.98:9090/targets

3. **Prometheus Alerts**
   - URL: http://5.223.52.98:9090/alerts

---

## 🎨 Grafana Tips

### Customize Time Range
- Top-right corner: Click time range (e.g., "Last 1 hour")
- Change to "Last 5 minutes" for real-time monitoring
- Use "Auto-refresh" (5s/10s/30s) for live updates

### Zoom into Graphs
- Click and drag on any graph to zoom
- Double-click to reset zoom
- Use panel inspector for detailed data

### Create Alerts
- Click any panel → Edit
- Go to Alert tab
- Configure threshold and notifications

### Export Dashboard
- Settings → JSON Model
- Save configuration
- Import on other Grafana instances

---

## 🔐 Security Note

⚠️ **Important:** Ports 3000 and 9090 are now publicly accessible on the internet!

**Recommendations:**

1. **Change Grafana password immediately** after first login

2. **Restrict access to your IP only:**
   ```bash
   # On server (requires sudo)
   sudo ufw delete allow 3000/tcp
   sudo ufw delete allow 9090/tcp
   sudo ufw allow from YOUR_WINDOWS_IP to any port 3000
   sudo ufw allow from YOUR_WINDOWS_IP to any port 9090
   ```

3. **Use SSH tunnel** (most secure):
   ```powershell
   # On Windows PowerShell
   ssh -L 3000:localhost:3000 -L 9090:localhost:9090 user@5.223.52.98
   ```
   Then access via `localhost` instead of IP.

4. **Set up HTTPS** for production use

---

## ✅ You're All Set!

**Open your Windows browser now and visit:**

### 🎯 http://5.223.52.98:3000

**Login with:**
- Username: `admin`
- Password: `admin`

**Then explore your production-grade monitoring dashboard!** 🚀

---

## 📞 Need Help?

If you can't connect:

1. Check the diagnostic output above
2. Verify firewall settings (may need sudo)
3. Check cloud security groups (AWS/Azure/GCP)
4. Try from different network (mobile hotspot test)

**Quick test from Windows PowerShell:**
```powershell
Test-NetConnection -ComputerName 5.223.52.98 -Port 3000
Test-NetConnection -ComputerName 5.223.52.98 -Port 9090
```

Should show: `TcpTestSucceeded: True`
