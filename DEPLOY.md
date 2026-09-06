# FareBharat — Live Deployment Guide (GitHub Actions + Streamlit Cloud)

Zero-cost, always-on setup. Judges get a public URL; scraper runs daily on
GitHub's servers and commits fresh data; dashboard auto-refreshes.

```
                  ┌────────────────────────────┐
                  │  GitHub Actions (cron)     │
                  │  daily 06:15 IST           │
                  │  runs scraper + index      │
                  │  commits data/apix.db      │
                  └──────────────┬─────────────┘
                                 │ git push
                                 ▼
                        ┌──────────────────┐
                        │   GitHub repo    │  (single source of truth)
                        └────────┬─────────┘
                                 │ auto-pull on commit
                                 ▼
                    ┌──────────────────────────┐
                    │  Streamlit Cloud         │  public URL
                    │  streamlit run           │  yourname.streamlit.app
                    │  apix/dashboard.py       │
                    └──────────────────────────┘
```

## Prerequisites

- A GitHub account
- A Streamlit Cloud account (free): https://share.streamlit.io
  - Sign in with GitHub — no card needed

## Step 1 — Create the GitHub repo

From the project folder (`apix/`):

```powershell
cd "D:\AI_VSCode\SIH 2026\apix"
git init
git add .
git commit -m "initial FareBharat prototype"
# create empty repo on github.com first (e.g. 'farebharat'), then:
git branch -M main
git remote add origin https://github.com/<your-username>/farebharat.git
git push -u origin main
```

**Important:** the repo must be **public** for the free Streamlit Cloud tier
(private repos also work but require the free "Streamlit Community Cloud" account).

## Step 2 — Enable the scraper workflow

Already committed: `.github/workflows/scrape.yml`.

- GitHub → your repo → **Actions** tab → enable workflows
- Click **FareBharat Daily Scrape** → **Run workflow** to trigger a first run manually
- After ~2 min you should see a new commit "auto: FareBharat APIx daily snapshot …"

The cron fires daily at 00:45 UTC (06:15 IST). Change the schedule inside
`.github/workflows/scrape.yml` if needed.

## Step 3 — Deploy the dashboard on Streamlit Cloud

1. Go to https://share.streamlit.io  →  **New app**
2. Pick your GitHub repo
3. Branch: `main`
4. Main file path: `dashboard.py`  *(if your repo root is `apix/`)*
   or `apix/dashboard.py` if you nested it
5. Click **Deploy**

First build takes ~3 min (Streamlit installs `requirements.txt`).
When done you get a public URL like `https://farebharat-<hash>.streamlit.app`.

## Step 4 — Test the loop

1. On GitHub → Actions → **Run workflow** manually
2. Wait for the green check
3. Refresh the Streamlit URL — new data appears (dashboard also auto-refreshes
   every 10 minutes)

## Live pipeline verification

- **Latest scrape date** shown in the sidebar KPI = date of last commit
- **Commit history** on GitHub = full audit trail (great for MoSPI judges)
- **Actions log** shows each scraper run, quote counts, and errors

## Troubleshooting

| Symptom | Fix |
|---|---|
| Workflow fails on `git push` | Repo → Settings → Actions → General → Workflow permissions → **Read and write** |
| Streamlit build fails on Playwright | Playwright is only needed by the scraper (runs in GitHub Actions), not by the dashboard. Nothing to fix — the dashboard reads the DB. |
| Dashboard shows "No data" | Run the workflow manually once (Step 2). Or locally: `python demo_data.py && python build_index.py && git add data/apix.db && git commit -m "seed" && git push` |
| All scrapers blocked | Workflow falls back to `demo_data.py` so the dashboard is never empty. |
| Want more frequent updates | Edit the `cron` line in the workflow (e.g. `"0 */6 * * *"` = every 6 hours). GitHub Actions minimum is 5 min. |

## Local development

```powershell
cd apix
pip install -r requirements.txt
python demo_data.py         # seed data
python build_index.py       # compute APIx
streamlit run dashboard.py  # open http://localhost:8501
```

## Cost

- GitHub Actions: 2,000 min/month free (this workflow uses ~5 min/day = 150/mo)
- Streamlit Community Cloud: free (1 GB RAM, unlimited public apps)
- Total: **₹0**
