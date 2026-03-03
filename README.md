# Range Gap Finder - SEO Competitor & Gap Analyser

A Streamlit app for SEO analysis: content gaps, competitive opportunities, and market share from your SEO data exports.

## Quick Start

**Prerequisites:** Python 3.8+ with pip

1. **Clone and go to the project:**
   ```bash
   cd streamlit_range_gap_finder
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   (Or use `scripts/requirements.txt` if you prefer.)

3. **Run the app:**
   ```bash
   streamlit run streamlit_app.py
   ```

4. Open **http://localhost:8501** in your browser.

No Redis, Docker, or Celery required.

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

## Deploying to Streamlit Community Cloud

- **Requirements:** Put `requirements.txt` in the **root** of the repo (same folder as `streamlit_app.py`). This repo already has it.
- **App settings:** Main file path: `streamlit_app.py`. Branch: `main`.
- **If you see `ModuleNotFoundError: No module named 'sentence_transformers'`:**
  1. Confirm `requirements.txt` is in the repo root on GitHub and you’ve pushed the latest commit.
  2. In the [Cloud dashboard](https://share.streamlit.io/), open your app → **⋮** → **Reboot app** (or **Clear cache and reboot**).
  3. If it still fails, try **Settings** → **Advanced settings** → set **Python version** to **3.11**, then save and redeploy (you may need to delete and recreate the app to change Python). Python 3.13 can miss wheels for some ML packages.

## Troubleshooting

- **Python not found (Windows)**  
  Use `python` not `python3`. Install from [python.org](https://www.python.org/downloads/) and check “Add Python to PATH”.

- **Port 8501 in use**  
  Stop the other app or run: `streamlit run streamlit_app.py --server.port 8502`

- **hdbscan build error (Windows)**  
  Install [Visual C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) or try:  
  `pip install hdbscan --only-binary :all:`  
  Clustering may still work with a fallback.

---

**Data:** CSV exports from SEO tools (e.g. Ahrefs, SEMrush) with keyword, URL, position, and optionally volume/traffic.
