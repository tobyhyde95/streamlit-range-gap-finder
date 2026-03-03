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
   pip install -r scripts/requirements.txt
   ```

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
├── seo_analyzer/         # Analysis logic (data load, clustering, reports)
├── scripts/
│   └── requirements.txt
├── validation_tests/     # Optional validation utilities
└── README.md
```

## Pushing to a new GitHub repo

1. **Commit your current work** (in the project folder):
   ```bash
   git add -A
   git status   # optional: check what will be committed
   git commit -m "Streamlit app; remove Overhaul lens and obsolete files"
   ```

2. **Create a new repository on GitHub**
   - Go to [github.com/new](https://github.com/new).
   - Choose a name (e.g. `streamlit-range-gap-finder`), visibility (Public/Private), and **do not** add a README, .gitignore, or license (you already have these locally).

3. **Point this project at the new repo and push**
   - Replace `YOUR_USERNAME` and `YOUR_REPO` with your GitHub username and the new repo name:
   ```bash
   git remote set-url origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git push -u origin main
   ```
   - If your default branch is `master` instead of `main`:
   ```bash
   git push -u origin master
   ```
   - If GitHub shows a different URL (e.g. SSH), use that instead:
   ```bash
   git remote set-url origin git@github.com:YOUR_USERNAME/YOUR_REPO.git
   git push -u origin main
   ```

4. **If you prefer to keep the old remote** and add the new one as a second remote:
   ```bash
   git remote add neworigin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git push -u neworigin main
   ```

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
