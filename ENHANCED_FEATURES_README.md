# Enhanced SEO Analysis System

This document describes the enhanced features added to the SEO analysis system, focusing on improved URL parsing, synonym discovery, and a human-in-the-loop approval workflow.

## Overview

The enhanced system provides:

1. **Improved Category Extraction**: Configurable URL parsing with identifier pattern recognition
2. **Enhanced Facet Normalization**: URL decoding and synonym-based normalization
3. **Synonym Discovery**: Automated detection of potential synonym rules
4. **Human-in-the-Loop Approval**: Web interface for reviewing and managing synonym suggestions
5. **Configuration Management**: Centralized JSON-based configuration system

## Key Components

### 1. Enhanced URL Parser (`seo_analyzer/url_parser.py`)

The `URLParser` class provides improved category extraction and facet normalization:

#### Category Extraction
- **Configurable Identifier Patterns**: Recognizes and ignores patterns like `^\d+$`, `^cat\d+$`, `^p-\d+$`
- **Reverse Order Processing**: Iterates through URL segments in reverse order
- **Stemming and Synonym Lookup**: Applies NLTK stemming and synonym dictionary lookup

#### Facet Normalization
- **URL Decoding**: Handles encoded characters like `%2F`
- **Synonym Mapping**: Maps variations to canonical keys
- **Consistent Formatting**: Standardizes facet key formats

#### Example Usage:
```python
from seo_analyzer.url_parser import URLParser

parser = URLParser()

# Extract category from URL
category = parser.extract_category_from_url("https://example.com/c/tools/drills/cat830704")
# Returns: "drill"

# Normalize facet key
normalized = parser.normalize_facet_key("Length (Mm)")
# Returns: "length_mm"
```

### 2. Synonym Discovery System (`seo_analyzer/synonym_discovery.py`)

The `SynonymDiscovery` class automatically identifies potential synonym rules:

#### Features:
- **Levenshtein Distance Calculation**: Finds similar terms using string similarity
- **Database Storage**: SQLite database for storing suggestions
- **Confidence Scoring**: Assigns confidence scores to suggestions
- **Bulk Operations**: Support for bulk approval/rejection

#### Example Usage:
```python
from seo_analyzer.synonym_discovery import SynonymDiscovery

discovery = SynonymDiscovery()

# Discover synonyms from URLs
urls = ["https://example.com/tools/drills?length_mm=100&screwlength=50"]
candidates = discovery.discover_synonyms_from_urls(urls)

# Store candidates in database
stored_ids = discovery.store_candidates(candidates)

# Get pending suggestions
suggestions = discovery.get_pending_suggestions()
```

### 3. Configuration Management (`seo_analyzer/config.json`)

Centralized configuration file for all normalization rules:

```json
{
  "identifier_patterns": [
    "^\\d+$",
    "^cat\\d+$",
    "^p-\\d+$"
  ],
  "category_synonyms": {
    "sdsdrills": "sds-drill"
  },
  "facet_synonyms": {
    "length (mm)": "length_mm",
    "screwlength": "length_mm",
    "diameter (mm)": "diameter_mm",
    "screwdiametermm": "diameter_mm"
  }
}
```

## API Endpoints

### GET `/api/suggestions`
Retrieves all pending synonym suggestions.

**Response:**
```json
[
  {
    "id": 1,
    "new_term": "screwlength",
    "suggested_mapping": "length_mm",
    "confidence_score": 0.85,
    "created_at": "2024-01-15T10:30:00"
  }
]
```

### POST `/api/suggestions/update`
Updates suggestion statuses (approve or reject).

**Request Body:**
```json
{
  "updates": [
    {"id": 1, "action": "approve"},
    {"id": 2, "action": "reject"}
  ]
}
```

**Response:**
```json
{
  "success_count": 2,
  "failure_count": 0
}
```

### POST `/api/suggestions/discover`
Discovers new synonyms from uploaded URLs.

**Request Body:**
```json
{
  "urls": [
    "https://example.com/tools/drills?length_mm=100&screwlength=50"
  ]
}
```

## Front-End Interface

### Synonym Review Page (`/suggestions-review.html`)

A modern, responsive web interface for managing synonym suggestions:

#### Features:
- **Data Table**: Sortable table with all pending suggestions
- **Bulk Actions**: Select multiple suggestions for approval/rejection
- **Confidence Indicators**: Color-coded confidence scores
- **Real-time Updates**: No page reload required after actions
- **Statistics Dashboard**: Overview of suggestion counts

#### Usage:
1. Navigate to `/suggestions-review.html`
2. Review pending suggestions in the table
3. Select individual or multiple suggestions using checkboxes
4. Click "Approve Selected" or "Reject Selected" buttons
5. View success/error messages in the notification area

## Integration with Existing System

### Enhanced Taxonomy Analysis (`seo_analyzer/enhanced_taxonomy_analysis.py`)

A drop-in replacement for the existing taxonomy analysis that uses the enhanced URL parser:

```python
from seo_analyzer.enhanced_taxonomy_analysis import _generate_enhanced_category_overhaul_matrix

# Use the enhanced function instead of the original
result = _generate_enhanced_category_overhaul_matrix(
    df, keyword_col, position_col, traffic_col, url_col, 
    onsite_df, volume_col, enable_synonym_discovery=True
)
```

## Testing

Run the test suite to verify functionality:

```bash
python test_enhanced_parser.py
```

This will test:
- Category extraction with various URL patterns
- Facet normalization with different input formats
- Synonym discovery and storage
- Configuration management

## Success Criteria Examples

### Category Extraction
- Input: `.../c/tools/drills/cat830704` → Output: `drill`
- Input: `.../tools/drills/sds-drills?brand=dewalt` → Output: `sds-drill`

### Facet Normalization
- Input: `Length (Mm)` → Output: `length_mm`
- Input: `Screwlength` → Output: `length_mm`
- Input: `diameter%20(mm)` → Output: `diameter_mm`

## Database Schema

The synonym discovery system uses a SQLite database with the following schema:

```sql
CREATE TABLE suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    new_term TEXT NOT NULL,
    suggested_mapping TEXT NOT NULL,
    confidence_score REAL NOT NULL,
    status TEXT DEFAULT 'pending_review',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Configuration

### Adding New Identifier Patterns
Edit `seo_analyzer/config.json` and add patterns to the `identifier_patterns` array:

```json
{
  "identifier_patterns": [
    "^\\d+$",
    "^cat\\d+$",
    "^p-\\d+$",
    "^sku-\\d+$"
  ]
}
```

### Adding Synonyms Programmatically
```python
from seo_analyzer.url_parser import URLParser

parser = URLParser()
parser.add_category_synonym("powertool", "power-tool")
parser.add_facet_synonym("tool_length", "length_mm")
```

## Deployment

1. Ensure all dependencies are installed:
   ```bash
   pip install -r scripts/requirements.txt
   ```

2. The system will automatically create the SQLite database and configuration file on first run.

3. Access the web interface at:
   - Main application: `http://localhost:5001/`
   - Synonym review: `http://localhost:5001/suggestions-review.html`

## Security

- API endpoints require the `X-API-KEY` header with value `my-secret-dev-key`
- Database files are stored locally in the `seo_analyzer/` directory
- Configuration files are read-only for the web application

## Troubleshooting

### Common Issues

1. **Database not found**: The system will automatically create the database on first run
2. **Configuration file not found**: A default configuration will be created automatically
3. **NLTK data missing**: Run `python -m nltk.downloader punkt` to install required NLTK data
4. **SpaCy model missing**: Run `python -m spacy download en_core_web_md` to install the SpaCy model

### Logs
Check the Flask application logs for detailed error messages and debugging information.

## Future Enhancements

Potential areas for future improvement:
- Machine learning-based synonym detection
- Integration with external taxonomy services
- Advanced confidence scoring algorithms
- Batch processing for large datasets
- Export/import functionality for configurations
