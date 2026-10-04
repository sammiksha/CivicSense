# 🚀 Deployment Guide: Vercel (Frontend) + Render (Backend)

This guide provides step-by-step instructions for deploying CivicSense (FinVision) with a decoupled production setup:
- **Backend (Python FastAPI)**: Hosted on **Render** (Free / Individual Web Service tier).
- **Frontend (Static SPA)**: Hosted on **Vercel** (Global Edge CDN).

---

## 🏗️ Architecture Overview

```
┌────────────────────────────────┐         API Calls (CORS enabled)         ┌────────────────────────────────┐
│        Vercel Frontend         │ ───────────────────────────────────────> │         Render Backend         │
│  (https://<app>.vercel.app)    │ <─────────────────────────────────────── │  (https://<app>.onrender.com)  │
└────────────────────────────────┘                                          └────────────────────────────────┘
```

---

## 📍 Part 1: Deploy Backend on Render

1. **Push your changes to GitHub**:
   ```bash
   git add .
   git commit -m "Configure project for Vercel + Render deployment"
   git push origin main
   ```

2. **Log into Render**:
   - Go to [render.com](https://render.com/) and log in with your GitHub account.

3. **Create a New Web Service**:
   - Click **New +** → **Web Service**.
   - Connect your GitHub repository (`CivicSense`).

4. **Service Settings**:
   - **Name**: `civicsense-backend` (or your preferred name)
   - **Region**: Choose the closest region (e.g. Singapore / Frankfurt / Oregon)
   - **Branch**: `main`
   - **Root Directory**: `backend` (or leave empty if using `render.yaml`)
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r backend/requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

5. **Environment Variables**:
   Add any optional production keys if needed:
   - `PYTHON_VERSION`: `3.11.0`
   - `ANTHROPIC_API_KEY`: *(Optional, for Claude AI explanations)*

6. **Deploy**:
   - Click **Create Web Service**.
   - Render will build and deploy the FastAPI backend.
   - Once deployed, copy your Render Web Service URL (e.g., `https://civicsense-backend.onrender.com`).
   - Test it by opening `https://civicsense-backend.onrender.com/health` in your browser.

---

## 📍 Part 2: Deploy Frontend on Vercel

1. **Log into Vercel**:
   - Go to [vercel.com](https://vercel.com/) and sign in with GitHub.

2. **Import Project**:
   - Click **Add New...** → **Project**.
   - Import your GitHub repository (`CivicSense`).

3. **Configure Project Settings**:
   - **Framework Preset**: `Other` / `Static HTML`
   - **Root Directory**: `./` (or `frontend`)
   - **Build Command**: Leave blank (static site)
   - **Output Directory**: `frontend` (if root directory is `./`) or leave default if root is set to `frontend`.

4. **Deploy**:
   - Click **Deploy**. Vercel will instantly publish your site on global CDN.
   - Your live frontend URL will be generated (e.g., `https://civicsense.vercel.app`).

---

## ⚙️ Connecting Frontend to Render Backend

The frontend `index.html` is equipped with automatic API URL resolution (`window.API_BASE_URL` & `getApiUrl()`).

You have two options to point the frontend to your Render URL:

### Option A: Automatic via Script Injection (Recommended)
Add this script tag in your `frontend/index.html` inside `<head>`:
```html
<script>
  window.API_BASE_URL = 'https://civicsense-backend.onrender.com';
</script>
```

### Option B: Dynamic via LocalStorage
Run this once in your browser DevTools Console on your Vercel deployment:
```js
localStorage.setItem('fv_api_base', 'https://civicsense-backend.onrender.com');
location.reload();
```

---

## ✅ Deployment Verification Checklist

- [x] FastAPI `/health` endpoint responds with `status: ok`
- [x] CORS middleware allows Vercel domain requests (`allow_origins=["*"]`)
- [x] Vercel SPA routing (`vercel.json`) redirects routes to `index.html`
- [x] Term sheet file uploads and PDF report downloads route correctly via `getApiUrl()`
