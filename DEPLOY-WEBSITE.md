# 🌍 Turn FX Live Analyst into a Website (open from any phone / PC — no command prompt!)

This guide makes your app a **real website** with a permanent address like:

```
https://yourname-fx-live-analyst.streamlit.app
```

Any device — your phone, tablet, a friend's laptop — just opens that link in a
browser. No Python, no command prompt, nothing to install. Your PC can be OFF;
the app still runs 24h on Streamlit's free cloud.

Cost: **RM 0 (free)**. Time: **~10 minutes**. You only click buttons on websites —
no typing commands anywhere.

---

## STEP 1 — Create a free GitHub account (stores your app's files)

1. Open **https://github.com** → click **Sign up** (top-right).
2. Enter an email, password, username → verify the email code.

## STEP 2 — Create a repository (a folder on GitHub)

1. Still on github.com, click the **+** (top-right) → **New repository**.
2. Repository name: `fx-live-analyst`
3. Choose **Public** (Streamlit Cloud free hosting requires public).
4. Click **Create repository**.

## STEP 3 — Upload the app files (drag & drop — no commands!)

1. On the new-repo page click **"uploading an existing file"** — or
   **Add file → Upload files**.
2. From your computer, drag in **everything INSIDE the `forex-app` folder**:
   `app.py`, `data_feed.py`, `mtf.py`, `chart_patterns.py`, `candle_patterns.py`,
   `indicators.py`, `signals.py`, `chart_view.py`, `requirements.txt`,
   `README.md`, and the **`static`** folder and **`.streamlit`** folder
   (drag the whole folders — GitHub uploads them as directories).
   > ⚠️ `app.py` must sit at the TOP level of the repo, not inside a subfolder.
3. Wait for the green upload bar to finish → click **Commit changes**.

## STEP 4 — Deploy on Streamlit Cloud (the free 24h host)

1. Open **https://share.streamlit.io** → click **Continue with GitHub** →
   **Authorize streamlit**.
2. Top-right **Create app** (or "New app") →
   **"Paste GitHub URL"** is easiest:
   ```
   yourname/fx-live-analyst
   ```
   (replace `yourname` with your GitHub username)
3. Main file path should read: `app.py` (it does by default).
4. Click **Deploy**. Wait 2–5 minutes while it installs the libraries from
   `requirements.txt` and boots.
5. 🎉 Done. Your website is now live at:
   `https://yourname-fx-live-analyst.streamlit.app`
   - Bookmark it, open it on your phone, share it with friends — it works from
     anywhere, even when your computer is off.
   - Every time you change a file in the GitHub repo, the site updates itself
     in a minute (redeploy from "Manage app" if needed).

### Optional — private OANDA token on the cloud
If you use an OANDA token, don't paste it in the sidebar on a public site.
In Streamlit Cloud: **Manage app → ⋮ → Settings → Secrets**, add:
```toml
OANDA_TOKEN = "your-token-here"
```
That's it — the app runs the same, and your token stays private.

## STEP 5 — Put it on your phone's home screen (feels like a real app)

1. Open your `.streamlit.app` link in **Chrome** (Android) or **Safari** (iPhone).
2. Browser menu (⋮ on Android, Share on iPhone) → **"Add to Home screen"**.
3. The **FX LIVE ANALYST icon** appears — it opens full-screen like a native app.

## STEP 6 (later, optional) — Publish on Google Play Store

Google Play only accepts Android packages, so wrap the *hosted* link:

1. Finish Steps 1–4 (the app must be online first).
2. Go to **https://www.pwabuilder.com** → paste your `.streamlit.app` URL →
   **Package for stores → Android** → download the `.aab` file.
   (Alternatives: median.co, webintoapp.com.)
3. Register a **Google Play Developer account** (one-time USD 25) at
   play.google.com/console → **Create app** → upload the `.aab` → fill the
   store listing → **Submit for review**.
4. After Google's review (a few days) your app is on the Play Store.

---

## FAQ

**Is Streamlit Cloud really free?**
Yes — the Community tier is free for public apps. Limits are generous (about
1 GB RAM per app, sleeps after long inactivity; the first visitor after a
sleep waits ~30 seconds, then everything is normal).

**Can friends in other countries open it?**
Yes — it's a normal https website. Anyone with the link can use it.

**Does the live chart still tick on the cloud version?**
Yes — the ticking runs in the visitor's browser (the page refreshes its own
chart every 2 s), so it behaves exactly like the local version.

**Weekend freeze?**
That's the real FX market resting (Sat ~05:00 → Mon ~05:00 MYT). Every platform
freezes then, including investing.com. The app shows a banner and resumes
automatically on Monday.
