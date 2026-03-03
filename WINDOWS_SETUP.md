# Complete Windows Setup Guide - Prometheus + Grafana

## Why You Need This

Currently, your metrics are **temporary** (stored in RAM). When you stop the agent, they're gone!

**This guide sets up:**
- ✅ **Prometheus** - Scrapes and permanently stores metrics
- ✅ **Grafana** - Beautiful dashboards to visualize your data
- ✅ **Persistent storage** - Metrics survive agent restarts

---

## Method 1: Docker Desktop (RECOMMENDED - Easiest)

### Step 1: Install Docker Desktop for Windows

1. **Download Docker Desktop:**
   - Go to: https://www.docker.com/products/docker-desktop/
   - Click "Download for Windows"
   - Run the installer (`Docker Desktop Installer.exe`)

2. **Installation Options:**
   - ✅ Enable WSL 2 (recommended)
   - ✅ Add shortcut to desktop
   - Click "Install"

3. **Restart your computer** when prompted

4. **Verify Docker is running:**
   ```powershell
   docker --version
   ```
   You should see: `Docker version 24.x.x`

---

### Step 2: Create Prometheus Configuration

Create a file called `prometheus.yml` in your project folder:

**Location:** `C:\Users\mzain\Python-projects\Commercial\nevoxai_server\nevoxai-project\prometheus.yml`

**Content:**
```yaml
global:
  scrape_interval: 15s  # Scrape metrics every 15 seconds
  evaluation_interval: 15s

scrape_configs:
  # Your voice agent metrics
  - job_name: 'nevox-voice-agents'
    static_configs:
      - targets: ['host.docker.internal:8000']  # IMPORTANT: Use host.docker.internal on Windows!
        labels:
          service: 'voice-agent'
```

**⚠️ IMPORTANT:** On Windows, use `host.docker.internal` instead of `localhost` so Docker can reach your agent!

---

### Step 3: Start Prometheus

Open **PowerShell** in your project folder and run:

```powershell
# Navigate to your project folder
cd C:\Users\mzain\Python-projects\Commercial\nevoxai_server\nevoxai-project

# Start Prometheus (this will store data in a Docker volume)
docker run -d `
  --name prometheus `
  -p 9090:9090 `
  -v ${PWD}/prometheus.yml:/etc/prometheus/prometheus.yml `
  -v prometheus-data:/prometheus `
  prom/prometheus
```

**Verify it's running:**
```powershell
docker ps
```

You should see `prometheus` in the list.

**Access Prometheus:**
- Open browser: http://localhost:9090
- Click "Status" → "Targets"
- You should see `nevox-voice-agents` with status **UP** (if your agent is running)

---

### Step 4: Start Grafana

```powershell
docker run -d `
  --name grafana `
  -p 3000:3000 `
  -v grafana-data:/var/lib/grafana `
  -e "GF_SECURITY_ADMIN_PASSWORD=admin" `
  grafana/grafana
```

**Access Grafana:**
- Open browser: http://localhost:3000
- Login: `admin` / `admin`
- You'll be prompted to change the password (you can skip this for now)

---

### Step 5: Connect Grafana to Prometheus

1. **In Grafana**, click the hamburger menu (≡) → **Connections** → **Data Sources**

2. Click **"Add data source"**

3. Choose **"Prometheus"**

4. Configure:
   - **Name:** `Prometheus`
   - **URL:** `http://host.docker.internal:9090`
   - **Access:** `Server (default)`

5. Scroll down and click **"Save & Test"**

   You should see: ✅ **"Data source is working"**

---

### Step 6: Import Your Dashboard

1. In Grafana, click **"+"** → **"Import dashboard"**

2. Click **"Upload JSON file"**

3. Select the `grafana-dashboard.json` file from your project folder

4. Click **"Load"**

5. Select **"Prometheus"** as the data source

6. Click **"Import"**

**You should now see your dashboard!** 📊

---

### Step 7: Test It!

1. **Start your agent:**
   ```powershell
   python agent-after-promotheus.py console
   ```

2. **Make a test call** (say hello, chat a bit, then goodbye)

3. **Check metrics are being collected:**
   ```powershell
   python view_metrics.py
   ```

4. **View in Grafana:**
   - Open http://localhost:3000
   - Go to your imported dashboard
   - You should see:
     - 💰 Total cost
     - 📞 Active calls
     - 📊 Token usage
     - 💾 Cache savings

5. **Stop and restart your agent** - Metrics should STILL be there! ✅

---

## Managing Docker Containers

### Useful Commands (PowerShell)

```powershell
# View running containers
docker ps

# View all containers (including stopped)
docker ps -a

# Stop containers
docker stop prometheus grafana

# Start containers
docker start prometheus grafana

# Restart containers
docker restart prometheus grafana

# View logs
docker logs prometheus
docker logs grafana

# Remove containers (WARNING: Will delete data if you don't have volumes!)
docker rm -f prometheus grafana

# Remove volumes (WARNING: Deletes all stored metrics!)
docker volume rm prometheus-data grafana-data
```

---

## Method 2: Native Windows Installation (Advanced)

If you don't want to use Docker:

### Install Prometheus (Native)

1. **Download:**
   - Go to: https://prometheus.io/download/
   - Download `prometheus-*.windows-amd64.zip`

2. **Extract:**
   - Extract to `C:\prometheus`

3. **Configure:**
   - Edit `C:\prometheus\prometheus.yml`:
   ```yaml
   scrape_configs:
     - job_name: 'nevox-agents'
       static_configs:
         - targets: ['localhost:8000']
   ```

4. **Run:**
   ```powershell
   cd C:\prometheus
   .\prometheus.exe
   ```

5. **Access:** http://localhost:9090

### Install Grafana (Native)

1. **Download:**
   - Go to: https://grafana.com/grafana/download?platform=windows
   - Download the Windows installer

2. **Install:**
   - Run the `.msi` installer
   - Follow the wizard

3. **Start Grafana:**
   - Grafana runs as a Windows service automatically
   - Or manually: `C:\Program Files\GrafanaLabs\grafana\bin\grafana-server.exe`

4. **Access:** http://localhost:3000

---

## Troubleshooting

### Problem: Prometheus shows target as "DOWN"

**Solution:**
1. Make sure your agent is running
2. Check agent metrics are exposed: http://localhost:8000/metrics
3. In `prometheus.yml`, use `host.docker.internal:8000` not `localhost:8000` (Docker)

### Problem: Grafana can't connect to Prometheus

**Solution:**
- Use `http://host.docker.internal:9090` as Prometheus URL (not `http://localhost:9090`)

### Problem: Metrics disappear when agent restarts

**Solution:**
- This is normal! Prometheus scrapes every 15 seconds
- Old data is preserved in Prometheus
- New data appears after ~15 seconds

### Problem: "host.docker.internal" doesn't work

**Solution:**
1. Make sure Docker Desktop is using WSL 2 backend
2. Or use the Docker container's internal IP:
   ```powershell
   docker network inspect bridge
   # Look for the Gateway IP (usually 172.17.0.1)
   # Use that IP instead
   ```

---

## What You'll See

Once everything is running:

### Prometheus (http://localhost:9090)
- Raw metrics data
- Query builder
- Target status

### Grafana (http://localhost:3000)
- 💰 **Cost Dashboard:** Real-time call costs
- 📊 **Token Usage:** Prompt, cached, completion tokens
- 📞 **Active Calls:** Current concurrent calls
- 💾 **Cache Hit Rate:** How much you're saving
- 📈 **Trends:** Historical data over time

---

## Moving to Production Server

Once you've tested on Windows:

1. **Export your Grafana dashboard:**
   - Click share icon → Export → Save JSON

2. **Copy config files to server:**
   - `prometheus.yml`
   - `grafana-dashboard.json`

3. **On Linux server, run:**
   ```bash
   # Start Prometheus
   docker run -d --name prometheus -p 9090:9090 \
     -v ./prometheus.yml:/etc/prometheus/prometheus.yml \
     -v prometheus-data:/prometheus \
     prom/prometheus

   # Start Grafana
   docker run -d --name grafana -p 3000:3000 \
     -v grafana-data:/var/lib/grafana \
     grafana/grafana

   # On Linux, use localhost:8000 instead of host.docker.internal
   ```

4. **Import dashboard in production Grafana**

---

## Summary

**Data Flow:**
```
Your Agent (:8000/metrics)
     ↓ (scraped every 15s)
Prometheus Server (stores in disk)
     ↓ (queries)
Grafana (beautiful dashboards)
```

**Benefits:**
- ✅ Persistent metrics (survive restarts)
- ✅ Historical data (days, weeks, months)
- ✅ Real-time monitoring
- ✅ Cost tracking
- ✅ Performance analysis

**Next Steps:**
1. Install Docker Desktop
2. Run the commands above
3. Start your agent
4. Watch the metrics flow in! 📊
