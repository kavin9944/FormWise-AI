# Phase 9: Public Deployment Guide – FormWise AI

This guide provides the complete, step-by-step deployment blueprint for taking FormWise AI from local development to production on high-reliability, zero-cost (free-tier) infrastructure.

---

## 1. System Architecture Overview

FormWise AI uses a decoupled **Two-Tier Public Architecture**:

```
+-------------------------------------------------------------+
|                      STUDENT BROWSER                        |
+-------------------------------------------------------------+
         |                                           |
         | (1) Web Traffic                           | (2) Auth & Profile
         v                                           v
+-----------------------------+             +----------------------+
|     NETLIFY (Edge CDN)      |             |     GOOGLE CLOUD     |
|   • Serves static HTML/CSS  |             | • Firebase Auth      |
|   • Proxies /api/* to Flask |             | • Cloud Firestore    |
|   • Custom Domain & SSL     |             |                      |
+-----------------------------+             +----------------------+
         | (3) API Calls (Reverse Proxy)
         v
+-------------------------------------------------------------+
|              RENDER / RAILWAY (Python Container)            |
|   • Production WSGI Server (Gunicorn)                       |
|   • REST API Endpoints (/api/upload, /api/analyse, etc.)    |
|   • PyMuPDF & Tesseract OCR Pipeline                        |
|   • ReportLab In-Memory PDF Generator                       |
+-------------------------------------------------------------+
         |
         | (4) Delimited AI Prompts
         v
+-------------------------------------------------------------+
|              GOOGLE GEMINI 3.5 FLASH-LITE API               |
+-------------------------------------------------------------+
```

---

## 2. Recommended Hosting Services (100% Free Tier)

| Component | Recommended Platform | Why Selected | Monthly Cost |
|---|---|---|:---:|
| **Frontend** | **Netlify** | Global Edge CDN, automated HTTPS, zero config for static sites, built-in reverse proxy (`_redirects`) eliminates CORS issues. | **$0.00** |
| **Backend API** | **Render (Web Service)** | Native Python runtime, automated Git deployments, supports Gunicorn WSGI, natively handles Secret Files (`serviceAccountKey.json`). | **$0.00** |
| **Database** | **Google Cloud Firestore** | Free Spark plan provides 1 GB storage, 50k reads/day, 20k writes/day. | **$0.00** |
| **Authentication** | **Firebase Auth** | Free up to 50,000 monthly active users (MAUs). | **$0.00** |
| **AI Inference** | **Google AI Studio (Gemini)** | Gemini 3.5 Flash-Lite free tier allowance (15 RPM / 1M TPM / 1,500 RPD). | **$0.00** |

---

## 3. Step-by-Step Deployment Instructions

### Step 3.1: Deploy Backend to Render (Free Web Service)
1. Push the repository to GitHub or GitLab.
2. Log in to [Render Dashboard](https://dashboard.render.com/).
3. Click **New +** -> **Web Service**.
4. Connect your FormWise AI Git repository.
5. Configure the service settings:
   - **Name**: `formwise-ai-api`
   - **Region**: Closest to your users (e.g., `Singapore` or `Frankfurt`).
   - **Branch**: `main`
   - **Root Directory**: (Leave blank or `.`)
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements-prod.txt`
   - **Start Command**: `gunicorn --chdir backend app:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120`
   - **Instance Type**: `Free`
6. Add **Secret File**:
   - In the **Environment** tab, scroll to **Secret Files**.
   - Filename: `serviceAccountKey.json`
   - Contents: Paste the complete contents of your private `backend/serviceAccountKey.json`.
   - File path on server will be `/etc/secrets/serviceAccountKey.json`.
7. Add **Environment Variables**:
   - `GEMINI_API_KEY`: `<Your-Google-Gemini-API-Key>`
   - `FIREBASE_SERVICE_ACCOUNT_PATH`: `/etc/secrets/serviceAccountKey.json`
   - `FLASK_DEBUG`: `0`
   - `PYTHON_VERSION`: `3.11.9`
8. Click **Deploy Web Service**.
9. Once live, test the endpoint:
   ```bash
   curl https://formwise-ai-api.onrender.com/health
   # Expected response: {"firebase_admin_initialized":true,"firestore_initialized":true,"status":"success"}
   ```

---

### Step 3.2: Configure Netlify Frontend
1. Open `frontend/_redirects` and `netlify.toml`.
2. Replace `YOUR_BACKEND_URL` with your actual Render URL:
   ```text
   /api/*  https://formwise-ai-api.onrender.com/api/:splat  200!
   /health https://formwise-ai-api.onrender.com/health  200!
   ```
3. Log in to [Netlify](https://app.netlify.com/).
4. Click **Add new site** -> **Import an existing project** (or drag & drop the `frontend` folder).
5. Configure build settings:
   - **Base directory**: (Leave blank)
   - **Publish directory**: `frontend`
   - **Build command**: (Leave blank — static site)
6. Click **Deploy Site**.
7. Note down your assigned Netlify domain (e.g., `https://formwise-ai.netlify.app`).

---

### Step 3.3: Whitelist Domain in Firebase
To prevent `auth/unauthorized-domain` errors when users sign in from Netlify:
1. Open the [Firebase Console](https://console.firebase.google.com/).
2. Select project **`formwise-ai-7caa9`**.
3. Navigate to **Authentication** -> **Settings** tab.
4. Click **Authorized domains** -> **Add domain**.
5. Enter your Netlify domain (e.g. `formwise-ai.netlify.app`).
6. Click **Save**.

---

## 4. Environment Variables Reference

| Variable Name | Required By | Environment | Description / Sample Value |
|---|:---:|:---:|---|
| `GEMINI_API_KEY` | Backend | Server | Google Gemini API Studio key (`AIzaSy...`) |
| `FIREBASE_SERVICE_ACCOUNT_PATH` | Backend | Server | Absolute path to secret file (`/etc/secrets/serviceAccountKey.json`) |
| `FLASK_DEBUG` | Backend | Server | Set to `0` in production |
| `PORT` | Backend | Server | Provided automatically by Render/Railway (e.g. `10000` or `5000`) |
| `PYTHON_VERSION` | Backend | Server | `3.11.9` or `3.12.0` |
| `window.FORMWISE_API_URL` | Frontend | Client | (Optional) Fallback backend URL if Netlify proxy is not used |

---

## 5. Storage Characteristics & Ephemeral Filesystem

### How File Storage Operates:
1. **Uploaded Documents (`uploads/{uid}/{doc_id}.pdf`)**:
   - On free-tier container hosting (Render / Railway), local disk storage is **ephemeral**.
   - During an active student session, files exist on disk for immediate extraction, analysis, checklist matching, and answer verification.
   - If the container restarts or spins down after inactivity (15 mins on Render Free), the container disk is recycled.
2. **Generated Summary PDFs (`/api/download-pdf`)**:
   - ReportLab generates the PDF **in-memory** (`io.BytesIO`) and streams it directly to the student's browser as a downloadable attachment.
   - Generated PDFs do not consume persistent server disk space.
3. **Database Metadata**:
   - All student profiles, document history, and confirmed checklist matches are stored permanently in **Google Cloud Firestore**.
4. **Zero-Cost Recommendation**:
   - The current architecture supports full end-to-end user workflows within their active session at $0.00 cost without requiring paid storage upgrades.
