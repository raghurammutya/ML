# External Access Guide - Prometheus & Grafana

Guide to access Prometheus and Grafana from your Windows laptop.

## ✅ Configuration Complete

The services are now configured to accept external connections on all network interfaces.

---

## 🌐 Access URLs

Replace `<SERVER_IP>` with your server's IP address: **5.223.52.98**

| Service | URL | Credentials |
|---------|-----|-------------|
| **Grafana** | http://5.223.52.98:3000 | admin / admin |
| **Prometheus** | http://5.223.52.98:9090 | No auth |

---

## 🔓 Firewall Configuration (May Require sudo)

### Check Current Firewall Status

```bash
# Check if UFW is active
sudo ufw status

# Check if firewalld is active
sudo systemctl status firewalld

# Check iptables rules
sudo iptables -L -n | grep -E "(3000|9090)"
```

### Option 1: UFW (Ubuntu Firewall)

```bash
# Allow Grafana (port 3000)
sudo ufw allow 3000/tcp

# Allow Prometheus (port 9090)
sudo ufw allow 9090/tcp

# Reload firewall
sudo ufw reload

# Check status
sudo ufw status
```

### Option 2: firewalld (CentOS/RHEL)

```bash
# Allow Grafana
sudo firewall-cmd --permanent --add-port=3000/tcp

# Allow Prometheus
sudo firewall-cmd --permanent --add-port=9090/tcp

# Reload firewall
sudo firewall-cmd --reload

# Check rules
sudo firewall-cmd --list-all
```

### Option 3: iptables (Manual)

```bash
# Allow Grafana
sudo iptables -A INPUT -p tcp --dport 3000 -j ACCEPT

# Allow Prometheus
sudo iptables -A INPUT -p tcp --dport 9090 -j ACCEPT

# Save rules (Ubuntu/Debian)
sudo netfilter-persistent save

# Save rules (CentOS/RHEL)
sudo service iptables save
```

### Option 4: Cloud Provider Security Groups

If you're on AWS, Azure, GCP, or other cloud providers:

1. **AWS EC2:**
   - Go to EC2 Console → Security Groups
   - Select your instance's security group
   - Add Inbound Rules:
     - Type: Custom TCP, Port: 3000, Source: Your IP or 0.0.0.0/0
     - Type: Custom TCP, Port: 9090, Source: Your IP or 0.0.0.0/0

2. **Azure:**
   - Go to Virtual Machine → Networking → Inbound port rules
   - Add port 3000 and 9090

3. **GCP:**
   - Go to VPC Network → Firewall Rules
   - Create rule for tcp:3000,9090

---

## 🧪 Testing Connectivity

### From Your Windows Laptop

**Test Prometheus:**

```powershell
# PowerShell
Invoke-WebRequest -Uri "http://5.223.52.98:9090/-/healthy" -UseBasicParsing

# Or use your web browser
# Navigate to: http://5.223.52.98:9090
```

**Test Grafana:**

```powershell
# PowerShell
Invoke-WebRequest -Uri "http://5.223.52.98:3000/api/health" -UseBasicParsing

# Or use your web browser
# Navigate to: http://5.223.52.98:3000
```

### From the Server (Verify Ports are Open)

```bash
# Test locally first
curl http://localhost:3000/api/health
curl http://localhost:9090/-/healthy

# Test external access
curl http://5.223.52.98:3000/api/health
curl http://5.223.52.98:9090/-/healthy
```

---

## 🔍 Troubleshooting

### Issue: Connection Refused from Windows

**Possible Causes:**
1. Firewall blocking ports 3000 and 9090
2. Cloud security group not configured
3. Network connectivity issue

**Solutions:**

1. **Check if ports are listening on all interfaces:**
   ```bash
   sudo netstat -tlnp | grep -E "(3000|9090)"
   # Should show 0.0.0.0:3000 and 0.0.0.0:9090
   ```

2. **Test from server itself:**
   ```bash
   curl http://5.223.52.98:3000/api/health
   ```
   - If this works but Windows can't connect → Firewall issue
   - If this fails → Configuration issue

3. **Check Docker port bindings:**
   ```bash
   docker port ticker-grafana
   docker port ticker-prometheus
   ```
   Should show:
   ```
   3000/tcp -> 0.0.0.0:3000
   9090/tcp -> 0.0.0.0:9090
   ```

4. **Restart containers:**
   ```bash
   cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/ticker_service/monitoring
   docker-compose -f docker-compose.monitoring.yml restart
   ```

### Issue: Grafana Login Not Working

**Solution:**
- Default credentials: `admin` / `admin`
- You'll be prompted to change password on first login
- If locked out, reset password:
  ```bash
  docker exec -it ticker-grafana grafana-cli admin reset-admin-password newpassword
  ```

### Issue: Dashboard Shows No Data

**Possible Causes:**
1. Ticker service not running on port 8000
2. Prometheus not scraping correctly

**Solutions:**

1. **Check Prometheus targets:**
   - Open http://5.223.52.98:9090/targets
   - `ticker-service` should be UP (green)

2. **If ticker-service is DOWN:**
   - Ensure ticker service is running on the server
   - Update `prometheus.yml` if needed (see below)

---

## 📝 Configuration for Ticker Service Access

If Prometheus can't reach the ticker service, you may need to update the target.

### Edit prometheus.yml

```bash
cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/ticker_service/monitoring
nano prometheus.yml
```

Find the `ticker-service` job and update the target:

```yaml
scrape_configs:
  - job_name: 'ticker-service'
    static_configs:
      - targets: ['host.docker.internal:8000']  # Docker Desktop (Mac/Windows)
      # OR
      - targets: ['172.17.0.1:8000']  # Linux Docker bridge
      # OR
      - targets: ['5.223.52.98:8000']  # Direct server IP
```

After editing, reload Prometheus:

```bash
curl -X POST http://5.223.52.98:9090/-/reload
```

---

## 🔐 Security Recommendations

⚠️ **Important:** These ports are now publicly accessible!

### 1. Restrict Access by IP (Recommended)

**UFW Example:**
```bash
# Remove existing rules
sudo ufw delete allow 3000/tcp
sudo ufw delete allow 9090/tcp

# Allow only from your Windows laptop IP (replace with your IP)
sudo ufw allow from YOUR_WINDOWS_IP to any port 3000
sudo ufw allow from YOUR_WINDOWS_IP to any port 9090
```

**iptables Example:**
```bash
# Allow only from specific IP
sudo iptables -A INPUT -p tcp -s YOUR_WINDOWS_IP --dport 3000 -j ACCEPT
sudo iptables -A INPUT -p tcp -s YOUR_WINDOWS_IP --dport 9090 -j ACCEPT

# Drop all other connections to these ports
sudo iptables -A INPUT -p tcp --dport 3000 -j DROP
sudo iptables -A INPUT -p tcp --dport 9090 -j DROP
```

### 2. Change Grafana Password

1. Login to Grafana: http://5.223.52.98:3000
2. You'll be prompted to change password
3. Use a strong password

### 3. Enable HTTPS (Optional)

For production, use nginx reverse proxy with SSL:

```bash
# Install nginx
sudo apt-get install nginx certbot python3-certbot-nginx

# Configure reverse proxy
# See nginx configuration examples online
```

### 4. Use VPN or SSH Tunnel (Most Secure)

Instead of exposing ports, use SSH tunnel from Windows:

```powershell
# PowerShell (run on Windows)
ssh -L 3000:localhost:3000 -L 9090:localhost:9090 user@5.223.52.98
```

Then access:
- Grafana: http://localhost:3000
- Prometheus: http://localhost:9090

---

## ✅ Quick Verification Checklist

- [ ] Docker containers running: `docker ps | grep ticker`
- [ ] Ports listening on 0.0.0.0: `netstat -tlnp | grep -E "(3000|9090)"`
- [ ] Firewall allows ports 3000 and 9090
- [ ] Cloud security group configured (if applicable)
- [ ] Can access from Windows browser: http://5.223.52.98:3000
- [ ] Grafana login works (admin/admin)
- [ ] Dashboard visible in Grafana
- [ ] Prometheus targets page loads: http://5.223.52.98:9090/targets

---

## 🚀 Access Now!

**From your Windows laptop, open your browser and visit:**

- **Grafana:** http://5.223.52.98:3000
- **Prometheus:** http://5.223.52.98:9090

**Grafana Login:**
- Username: `admin`
- Password: `admin`
- Change password on first login

**Once in Grafana:**
1. Go to Dashboards (☰ menu)
2. Look for "Tick Processing - Performance & Health"
3. Enjoy your monitoring dashboard!

---

## 📞 Need Help?

If you can't connect:

1. **Run this diagnostic command on the server:**
   ```bash
   cd /mnt/stocksblitz-data/Quantagro/tradingview-viz/ticker_service/monitoring
   ./diagnose-connectivity.sh
   ```

2. **Check the firewall is the issue:**
   - If `curl http://localhost:3000` works but Windows can't connect → Firewall
   - If `curl http://5.223.52.98:3000` works from server → Cloud/network issue

3. **Share the output of:**
   ```bash
   docker ps | grep ticker
   sudo ufw status
   sudo netstat -tlnp | grep -E "(3000|9090)"
   ```
