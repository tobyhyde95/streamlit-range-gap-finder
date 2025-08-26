# Range Gap Finder - SEO Competitor & Gap Analyzer

A comprehensive web application for advanced SEO analysis, designed to identify content gaps, competitive opportunities, and market share insights from your SEO data exports.

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Docker (for Redis)
- Git

### Running the Application

1. **Clone and navigate to the project:**
   ```bash
   cd range_gap_finder
   ```

2. **Start the application:**
   ```bash
   ./scripts/start.sh
   ```

3. **Access the frontend:**
   Open your browser and go to: **http://localhost:5000**

   The application will automatically serve the main interface at this URL.

## 📋 What the Application Does

This tool analyzes your SEO data exports to provide:

- **Content Gaps**: Keywords where competitors rank but you don't
- **Competitive Opportunities**: Keywords where competitors outrank you
- **Market Share Analysis**: Traffic distribution between domains
- **Taxonomy & Architecture Analysis**: Category and facet structure insights

## 🔧 Application Architecture

- **Frontend**: Modern web interface with interactive tables and filtering
- **Backend**: Flask API with Celery for background processing
- **Database**: Redis for task queue management
- **Processing**: Asynchronous analysis with real-time progress updates

## 📁 Project Structure

```
range_gap_finder/
├── assets/                 # Frontend assets (CSS, JS)
├── seo_analyzer/          # Python backend code
├── scripts/               # Startup scripts
├── range-gap-finder.html  # Main frontend interface
├── Procfile              # Process configuration
└── README.md             # This file
```

## 🎯 How to Use

1. **Upload Data**: Upload your domain's SEO export and competitor exports
2. **Map Columns**: Automatically map or manually configure column mappings
3. **Configure Analysis**: Select which analysis types to run
4. **Run Analysis**: Submit and monitor progress in real-time
5. **Explore Results**: Use the interactive interface to explore insights

## 🔍 Available Analysis Types

- **Content Gaps** (Individual Keywords & Topic Groups)
- **Competitive Opportunities** (Individual Keywords & Topic Groups)  
- **Market Share Analysis** (Individual Keywords & Topic Groups)
- **Taxonomy & Architecture Analysis** (Category Overhaul Matrix & Facet Potential)

## 🛠️ Development

For development setup and Git workflow instructions, see `scripts/README.md`.

## 📞 Support

If you encounter any issues:
1. Check that Redis is running: `docker ps | grep redis`
2. Verify the application is running on port 5000
3. Check the terminal logs for any error messages

---

**Note**: The application requires CSV exports from SEO tools (like Ahrefs, SEMrush, etc.) with keyword, URL, position, and traffic data.
