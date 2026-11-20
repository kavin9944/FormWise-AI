# FormWise AI – Public Demo Setup Guide

This guide tells **you (the host)** everything you need to do before sharing the public link with teammates.

---

## What This Achieves

| Before | After |
|---|---|
| Two URLs (frontend :8000, backend :5000) | **ONE public HTTPS link** |
| Works only on your laptop | Works on **any teammate's device** |
| Requires Python installed | **No installation needed** for teammates |

---

## Step 1 – Prerequisites on Your Laptop

Make sure the following are already installed and working:

- ✅ **Python 3.x** (you already have this)
- ✅ **Virtual environment** (`venv/` folder exists – run `setup.bat` if missing)
- ✅ **`.env` file** with a valid `GEMINI_API_KEY`
- ✅ **Tesseract OCR** installed (for document extraction)

---

## Step 2 – Install ngrok (One-Time Setup)

ngrok creates a secure public HTTPS tunnel to your laptop.

### Option A – Automatic (Recommended)
`START_PUBLIC_DEMO.bat` will automatically download `ngrok.exe` if it is not found.

### Option B – Manual Download
1. Go to [https://ngrok.com/download](https://ngrok.com/download)
2. Download the **Windows (64-bit)** ZIP file.
3. Extract **`ngrok.exe`** directly into `D:\ASTRON\FormWise-AI\`

---

## Step 3 – Create a Free ngrok Account (One-Time Setup)

You need a free ngrok account to get a stable authtoken.

1. Sign up at: [https://dashboard.ngrok.com/signup](https://dashboard.ngrok.com/signup)
2. After logging in, go to: [https://dashboard.ngrok.com/get-started/your-authtoken](https://dashboard.ngrok.com/get-started/your-authtoken)
3. Copy your **Authtoken**.
4. Open **Command Prompt** and run:
   ```
   ngrok config add-authtoken YOUR_TOKEN_HERE
   ```
   Replace `YOUR_TOKEN_HERE` with your actual token.

> **This only needs to be done once per laptop.**

---

## Step 4 – Add ngrok Domain to Firebase Authorized Domains

Firebase blocks authentication from unknown domains by default.  
You must add the ngrok domain so your teammates can log in.

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select your project: **formwise-ai-7caa9**
3. Navigate to: **Authentication → Settings → Authorized domains**
4. Click **Add domain**
5. Add exactly: `ngrok-free.app`
6. Click **Save**

> This covers **all** `*.ngrok-free.app` subdomains automatically, so you do not need to add a new domain every time the URL changes.

---

## Step 5 – Start the Demo

Double-click `START_PUBLIC_DEMO.bat`

The script will:
1. Activate your virtual environment
2. Start the Flask backend on port 5000 (serving frontend + API)
3. Start the ngrok HTTPS tunnel
4. Display your **ONE public link** automatically

---

## Step 6 – Share the Link

The public link looks like:
```
https://xxxx-xx-xx-xxx-xxx.ngrok-free.app
```

Share this link with your teammates via WhatsApp, email, or any messaging app.

---

## Important Notes

| Topic | Details |
|---|---|
| **Your laptop must stay ON** | Yes. The demo runs on your laptop. Close the bat windows to stop it. |
| **Link changes on restart** | Yes (free plan). Every time you run `START_PUBLIC_DEMO.bat`, a new URL is generated. Tell teammates the new link. |
| **Uploaded files** | Files uploaded by teammates are stored **temporarily** in `uploads/` on your laptop only. They are **not** backed up to the cloud. |
| **Secrets** | Your Gemini API key and Firebase service account JSON stay on your laptop only. They are never sent to the browser. |
| **Firestore data** | Student profiles and form data are saved in Firebase Firestore (cloud) – they persist even after stopping the demo. |
| **ngrok free plan limit** | 1 active tunnel, 40 req/min. Sufficient for a team demo. |

---

## Stopping the Demo

Either:
- Press any key in the `START_PUBLIC_DEMO.bat` window, **or**
- Double-click `STOP_PUBLIC_DEMO.bat`

Both methods stop Flask and ngrok cleanly.
