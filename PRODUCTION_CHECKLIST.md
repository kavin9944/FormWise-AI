# FormWise AI – Production Deployment Checklist

Use this checklist to track every step of the Phase 9 public deployment process.

---

## 1. Pre-Deployment Readiness (Codebase & Assets)

- [x] All 25 backend unit and integration tests passing (`python -m unittest discover -s backend -p "test_*.py"`).
- [x] All 15 readiness scoring unit tests passing (`python backend/scoring.py`).
- [x] All 6 client JavaScript files validated without syntax errors (`node -c`).
- [x] All 10 Python backend files compiled cleanly (`python -m py_compile`).
- [x] `requirements-prod.txt` created with `gunicorn>=21.2.0`.
- [x] `Procfile` created specifying `gunicorn --chdir backend app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120`.
- [x] `netlify.toml` and `frontend/_redirects` created with proxy rules for API routes.
- [x] Zero private keys, passwords, or `.env` files committed to Git.
- [x] Clean submission archive generated (`FormWise-AI-Team-Edition.zip`, 156 KB).

---

## 2. Backend Deployment Checklist (Render / Railway)

- [ ] Git repository connected to cloud host.
- [ ] Runtime set to Python 3.11+.
- [ ] Build command configured: `pip install -r requirements-prod.txt`.
- [ ] Start command verified: `gunicorn --chdir backend app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120`.
- [ ] Secret file uploaded: `serviceAccountKey.json` mounted at `/etc/secrets/serviceAccountKey.json`.
- [ ] Environment variable set: `FIREBASE_SERVICE_ACCOUNT_PATH=/etc/secrets/serviceAccountKey.json`.
- [ ] Environment variable set: `GEMINI_API_KEY=<valid_production_gemini_key>`.
- [ ] Environment variable set: `FLASK_DEBUG=0`.
- [ ] Health check verified: `GET https://<backend-url>/health` returns HTTP 200 with `status: success`.

---

## 3. Frontend Deployment Checklist (Netlify)

- [ ] `frontend/_redirects` updated with the actual production backend URL.
- [ ] `netlify.toml` verified with `publish = "frontend"`.
- [ ] Site deployed to Netlify.
- [ ] Custom domain or Netlify subdomain generated (`https://<app-name>.netlify.app`).
- [ ] Landing page loads over HTTPS with HTTP 200.
- [ ] Assets load without 404s (`css/style.css`, `js/api.js`, `js/auth.js`, etc.).
- [ ] Netlify edge proxy verified: `GET https://<app-name>.netlify.app/health` returns backend status.

---

## 4. Firebase Configuration Checklist

- [ ] Netlify domain added to Firebase Console under **Authentication -> Settings -> Authorized domains**.
- [ ] Firebase web client config verified in `frontend/js/firebase.js`.
- [ ] Student login tested on live Netlify domain.
- [ ] Student registration tested on live Netlify domain.
- [ ] Firestore read/write operations verified on student profile.

---

## 5. Post-Deployment End-to-End Verification

- [ ] Complete live login on Netlify URL.
- [ ] Upload sample PDF application form (`POST /api/upload`).
- [ ] Verify Gemini bilingual analysis generates field cards (`POST /api/analyse`).
- [ ] Test profile autofill on live form.
- [ ] Validate filled answers with client and server feedback (`POST /api/validate`).
- [ ] Confirm supporting document checklist match (`POST /api/checklist/confirm`).
- [ ] Verify Application Readiness score reaches expected level (`POST /api/readiness`).
- [ ] Preview form summary on live domain (`POST /api/preview`).
- [ ] Download generated summary PDF and inspect contents (`POST /api/download-pdf`).
