# Deploy guide — VC Scout

Target: **$0/mo** setup so anyone can add sources, run scans, and share state.

- Backend (FastAPI + Playwright) → Render free web service
- Database (Postgres) → Neon free tier (0.5 GB, always-on)
- Frontend → Vercel (already deployed)

## 1. Create a Neon Postgres database

1. Go to https://neon.tech and sign up (GitHub login is fine).
2. Create a new project — any region close to you.
3. After it provisions, open **Dashboard → Connection Details** and copy the
   `postgresql://...` connection string (click "Show password" first).
4. Keep this tab open. You'll paste this URL into Render in step 2.

## 2. Deploy the backend to Render

1. Push the new files to GitHub (see "Push changes" at the bottom).
2. Go to https://render.com and sign up with GitHub.
3. Click **New → Blueprint**, pick the `omer475/vc-scout-app` repo. Render will
   detect `render.yaml` and propose creating a `vc-scout-backend` service.
4. Before clicking "Apply", fill in the env vars it prompts for:
   - `DATABASE_URL` → paste the Neon URL from step 1.
   - `CORS_ORIGINS` → your Vercel URL, e.g.
     `https://vc-scout-app.vercel.app` (no trailing slash, no `/api`).
   - `GOOGLE_API_KEY` → copy from your local `backend/.env`.
5. Click **Apply**. First build takes ~5 min (Playwright image is big).
6. Once it shows "Live", copy the service URL, e.g.
   `https://vc-scout-backend.onrender.com`.

Free-tier note: the service spins down after 15 min idle. First request after
that waits 30–60 s for cold start, then it's snappy. Scans in progress keep it
awake.

## 3. Point the frontend at Render

In the Vercel dashboard for `vc-scout-app`:

1. **Settings → Environment Variables** → add / edit:
   - `VITE_API_URL` = `https://vc-scout-backend.onrender.com` (from step 2).
   - `VITE_STATIC` = `0` (or delete it — default is live mode).
2. **Deployments → latest → ⋯ → Redeploy** (un-check "Use existing build cache").

## 4. First-time seed (once, from any browser)

Open the deployed site, go to **Topics** → click "Seed defaults". Then
**Sources** → "Seed Turkish sources". Now anyone else can add more and run
scans; the data lives in Neon and is shared.

## Push changes to GitHub

```
cd ~/vc-scout-app
git add -A
git commit -m "Add Render deploy: Dockerfile, render.yaml, env-driven DB + API URL"
git push origin main
```

## Local dev still works

No env vars needed locally — `DATABASE_URL` defaults to SQLite and
`VITE_API_URL` defaults to `http://localhost:8000`. Run `./start.sh` as before.
