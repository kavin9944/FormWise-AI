# FormWise AI – Deployment Blockers & Technical Limitations

This document identifies potential deployment hurdles, free-tier hosting trade-offs, and their mitigation strategies before initiating Phase 9, Step 2.

---

## 1. Active Deployment Blockers (Action Required Prior to Deployment)

| # | Blocker | Impact | Mitigation Strategy | Owner |
|---|---|---|---|:---:|
| **1** | **Backend Host URL Not Yet Known** | Netlify `_redirects` requires the real backend URL (`https://<app>.onrender.com`). | Deploy the backend Web Service on Render first to obtain the live domain, then update `_redirects` before deploying to Netlify. | Developer |
| **2** | **Firebase Authorized Domain Whitelist** | Without adding the Netlify domain, Firebase Auth will block login with `auth/unauthorized-domain`. | Add the generated Netlify domain (e.g. `formwise-ai.netlify.app`) in the Firebase Console under **Authentication -> Settings -> Authorized domains**. | Developer |
| **3** | **Service Account Key Injection** | Backend needs `serviceAccountKey.json` to verify tokens and query Firestore. | On Render, add `serviceAccountKey.json` as a **Secret File** mounted at `/etc/secrets/serviceAccountKey.json`, and set `FIREBASE_SERVICE_ACCOUNT_PATH=/etc/secrets/serviceAccountKey.json`. | Developer |
| **4** | **Gemini API Key Provisioning** | Form analysis requires a valid `GEMINI_API_KEY`. | Add `GEMINI_API_KEY` to Render Environment Variables. Ensure the key has quota allocated on Google AI Studio. | Developer |

---

## 2. Free-Tier Platform Limitations & Trade-Offs

### 2.1 Render Free Tier Spin-Down (Cold Starts)
- **Behavior**: Render free instances automatically spin down (sleep) after 15 minutes of inactivity.
- **Impact**: The initial request after a period of dormancy may take 30 to 50 seconds while the container wakes up.
- **Mitigation**:
  - The frontend `api.js` has a background health check (`/health`) that runs on page load, waking up the server while the user reads the landing page.
  - Optional: Use a free uptime monitor (e.g., UptimeRobot or Cron-job.org) to ping `/health` every 10 minutes to keep the instance warm during demonstrations.

### 2.2 Ephemeral Container Filesystem
- **Behavior**: Uploaded PDFs stored on the container filesystem (`uploads/{uid}/{doc_id}.pdf`) are discarded when the container restarts.
- **Impact**: If a student returns to a previous upload after the server has slept, the PDF file on disk may no longer exist (causing 404 on re-analysis).
- **Mitigation**:
  - In an active student session (upload -> analysis -> autofill -> validate -> PDF download), everything completes seamlessly without issue.
  - Document metadata remains preserved in Firestore.
  - Future improvement: Upgrade to Firebase Cloud Storage (free tier allows 5 GB) for permanent file persistence across restarts.

### 2.3 Gemini API Free-Tier Quota
- **Behavior**: Free-tier Google AI Studio keys have a rate limit of 15 Requests Per Minute (RPM) and 1,500 Requests Per Day (RPD).
- **Impact**: Rapid burst testing by multiple users simultaneously could encounter HTTP 429 rate-limiting.
- **Mitigation**:
  - The backend caching mechanism (`_analysis_cache`) eliminates repeat Gemini calls for the same document.
  - Using `gemini-3.5-flash-lite` minimizes latency and quota consumption.

---

## 3. Summary of Decisions Requiring User Approval

1. **Approval to use Render Free Web Service** for backend hosting.
2. **Approval to use Netlify Free Starter Tier** for frontend hosting.
3. **Approval to keep local session-based storage** on the free tier (no paid storage plans).
4. **Approval to proceed to Phase 9, Step 2** (actual deployment execution).
