# Range Gap Finder - SEO Competitor & Gap Analyser

A Streamlit app for SEO analysis: content gaps, competitive opportunities, and market share from your SEO data exports. **Run it on Streamlit (hosted)** — no local server.

## Quick Start — Run on Streamlit

1. **Deploy the app** on [Streamlit Community Cloud](https://share.streamlit.io/):
   - Sign in with GitHub.
   - **New app** → choose repo **tobyhyde95/streamlit-range-gap-finder**, branch **main**, main file **streamlit_app.py**.
   - Click **Deploy**. Streamlit will install dependencies from the repo’s `requirements.txt` and host the app.

2. **Use the app** at the URL Streamlit gives you (e.g. `https://yourapp-name.streamlit.app`). Upload your CSVs, map columns, choose lenses, and run analysis there. No localhost or local run needed.

## What it does

- **Content Gaps** – Keywords competitors rank for but you don’t (individual + topic groups).
- **Competitive Opportunities** – Keywords where competitors outrank you (individual + topic groups).
- **Market Share** – Traffic distribution across domains (individual + topic groups).

## How to use

1. **Upload data** – Your domain CSV and one or more competitor CSVs (optional: on-site search CSV).
2. **Map columns** – Set Keyword, Position, and URL columns; optionally Volume and Traffic.
3. **Choose lenses** – Tick Content Gaps, Competitive Opportunities, and/or Market Share.
4. **Run analysis** – Click “Run analysis” and wait for results.
5. **Explore & export** – Use the tabs and “Download CSV” buttons.

## Project structure

```
streamlit_range_gap_finder/
├── streamlit_app.py      # Streamlit UI and entry point
├── requirements.txt      # Dependencies (root = for Streamlit Cloud)
├── seo_analyzer/         # Analysis logic (data load, clustering, reports)
├── scripts/
│   └── requirements.txt
├── validation_tests/     # Optional validation utilities
└── README.md
```

## Pushing to this GitHub repo

Repo: **https://github.com/tobyhyde95/streamlit-range-gap-finder**

1. **Commit your current work** (in the project folder):
   ```bash
   git add -A
   git status   # optional: check what will be committed
   git commit -m "Streamlit app; remove Overhaul lens and obsolete files"
   ```

2. **Point this project at the repo and push** (HTTPS):
   ```bash
   git remote set-url origin https://github.com/tobyhyde95/streamlit-range-gap-finder.git
   git push -u origin main
   ```
   If your branch is `master` instead of `main`:
   ```bash
   git push -u origin master
   ```

3. **Alternatively, use SSH** (if you use SSH keys):
   ```bash
   git remote set-url origin git@github.com:tobyhyde95/streamlit-range-gap-finder.git
   git push -u origin main
   ```

## Streamlit Cloud — tips

- **Requirements:** `requirements.txt` is in the repo root; Cloud uses it automatically. Main file: `streamlit_app.py`, branch: `main`.
- **If you see `ModuleNotFoundError: No module named 'sentence_transformers'`:**
  1. Confirm `requirements.txt` is in the repo root on GitHub and you’ve pushed the latest commit.
  2. In the [Cloud dashboard](https://share.streamlit.io/), open your app → **⋮** → **Reboot app** (or **Clear cache and reboot**).
  3. If it still fails, try **Settings** → **Advanced settings** → set **Python version** to **3.11**, then save and redeploy (you may need to delete and recreate the app to change Python). Python 3.13 can miss wheels for some ML packages.

## Running locally (optional)

Only if you want to run the app on your machine (e.g. for development):

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Then open the URL shown in the terminal (usually http://localhost:8501). For normal use, run the app on Streamlit Cloud instead.

---

**Data:** CSV exports from SEO tools (e.g. Ahrefs, SEMrush) with keyword, URL, position, and optionally volume/traffic.
