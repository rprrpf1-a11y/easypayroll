# EasyPayroll — Deployment Guide

This guide covers deploying **EasyPayroll** for free or low cost, whether to cloud platforms or self-hosted servers.

---

## 🚀 Option 1: Free Cloud Deployment on Render (Recommended)

Render provides a 100% free web service tier with automated SSL (HTTPS), custom domain support, and auto-deploy from GitHub.

1. **Push your code to GitHub**:
   ```bash
   git init
   git add .
   git commit -m "Initial commit of EasyPayroll"
   git branch -M main
   git remote add origin https://github.com/<your-username>/easypayroll.git
   git push -u origin main
   ```

2. **Connect to Render**:
   - Go to **[render.com](https://render.com)** and create a free account.
   - Click **New +** > **Web Service**.
   - Select your `easypayroll` repository.

3. **Configure Settings**:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python run_production.py`
   - Click **Create Web Service**.

Render will automatically build and deploy your app with a public HTTPS link (e.g. `https://easypayroll-xyz.onrender.com`).

---

## ⚡ Option 2: Deploy with Docker

A production-ready `Dockerfile` and `.dockerignore` are included in the repository.

1. **Build the Docker Image**:
   ```bash
   docker build -t easypayroll .
   ```

2. **Run the Container**:
   ```bash
   docker run -d -p 5000:5000 -v payroll_data:/app/payroll.db --name easypayroll_app easypayroll
   ```
   *(The `-v payroll_data:/app/payroll.db` flag ensures your SQLite payroll records persist across container restarts).*

---

## 🏢 Option 3: In-Office / Self-Hosted Server (Windows or Linux)

To run EasyPayroll on an office computer or local dedicated server:

1. **Install requirements**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the production server**:
   ```bash
   python run_production.py
   ```

3. **Access from other devices**:
   - Local: `http://localhost:5000`
   - Office Network: `http://<SERVER-IP-ADDRESS>:5000` (e.g., `http://192.168.1.120:5000`)

---

## 🔒 Production Security Checklist

- [x] **Production WSGI Server**: Waitress is configured with 8 concurrent worker threads.
- [x] **Concurrency & Integrity**: SQLite WAL mode enabled to handle simultaneous database reads/writes without locking.
- [x] **Data Isolation**: Multi-tenant database schema isolates all user and employee data.
- [x] **One-Click Backups**: Download `.db` database snapshots directly from the Settings menu.
- [ ] **HTTPS / SSL**: For internet access, always route traffic through Render, Cloudflare, or an Nginx reverse proxy with SSL enabled.
