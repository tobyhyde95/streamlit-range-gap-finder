# Python SEO Analyzer Application

## Project Overview

This is a web application for advanced SEO analysis. [cite_start]It's built with Python using the Flask framework for the web interface and Celery for handling long-running analysis tasks in the background[cite: 1]. The application uses a Redis server as a message broker for these background tasks.

---
## How to Run the Application

The project includes a startup script to run the web server and the background worker.

1.  Open the terminal in your project's root directory.
2.  Run the start script:
    ```bash
    ./start.sh
    ```
    This script ensures the Redis container is running and then uses `honcho` to start the `web` and `worker` processes. The application will then be available at `http://127.0.0.1:5000`.

---
## Project Setup and First-Time Backup

Follow these steps **one time** to get your project folder connected to and backed up on GitHub.

### Step 1: Install Git & Create a GitHub Account
* **Install Git**: Open the terminal and type `git --version`. If it's not installed, your Mac will prompt you to install it.
* **Create a GitHub Account**: Sign up for a free account at [GitHub.com](https://github.com/).

### Step 2: Create a `.gitignore` File
This file tells Git to ignore certain files and folders that shouldn't be backed up.
1.  In VS Code, create a new file in your project's root directory named exactly `.gitignore`.
2.  Paste the following content into it:
    ```
    # Virtual Environment
    venv/

    # Python cache
    __pycache__/
    *.pyc

    # Analysis cache from analysis.py
    cachedir/

    # Mac-specific files
    .DS_Store
    ```

### Step 3: Create a Private GitHub Repository
1.  Log in to GitHub.com.
2.  Click the **+** icon (top-right) and select **New repository**.
3.  Name your repository (e.g., `seo-analyzer-app`).
4.  Select **Private**. This is critical to keep your code and API keys secure.
5.  Leave all checkboxes for `README`, `license`, and `.gitignore` **unchecked**.
6.  Click **Create repository**. Keep this page open to copy the repository URL.

### Step 4: Upload Your Project
Run these commands in your VS Code terminal to upload your code.
1.  **Initialize Git**:
    ```bash
    git init
    ```
2.  **Set your identity** (replace with your name and the email you use for GitHub):
    ```bash
    git config --global user.name "Your Name"
    git config --global user.email "you@example.com"
    ```
3.  **Stage all your files** for the first backup:
    ```bash
    git add .
    ```
4.  **Save your first snapshot** (commit):
    ```bash
    git commit -m "Initial commit of SEO analyzer application"
    ```
5.  **Connect your local folder to GitHub** (replace `[YOUR_REPOSITORY_URL]` with the URL from Step 3):
    ```bash
    git remote add origin [YOUR_REPOSITORY_URL]
    ```
6.  **Rename the branch** to `main`:
    ```bash
    git branch -M main
    ```
7.  **Push your project** to GitHub:
    ```bash
    git push -u origin main
    ```

---
## Saving Daily Changes (Regular Workflow)

Follow these three steps every time you modify your code and want to save a new version.

### Step 1: Stage Your Changes
This command prepares all your modified files for saving.
```bash
git add .
```

### Step 2: Save a Snapshot (Commit)
This saves your staged files. Write a short, descriptive message in the quotes to describe your changes.
```bash
git commit -m "Your descriptive message here"
```

### Step 3: Upload to GitHub (Push)
This command uploads your saved snapshot to your GitHub backup.
```bash
git push
```