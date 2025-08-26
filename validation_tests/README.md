# Validation Tests

This folder contains all validation and testing components for the Category Overhaul Matrix analysis.

## Contents

### `category_mapping_validator.py`
The main validation module that automatically validates category mapping logic in Category Overhaul Matrix analysis.

**Features:**
- Automatically validates URL-to-category mapping logic
- Analyzes each unique row in the Category Overhaul Matrix
- Generates detailed validation reports
- Identifies specific issues with category extraction
- Provides accuracy statistics and common issue patterns

**Usage:**
```python
from category_mapping_validator import validate_category_overhaul_matrix_automation

# Validate matrix data
validation_results = validate_category_overhaul_matrix_automation(matrix_data)
```

### `TEST RESULTS/`
Directory containing validation reports and test outputs.

**Files:**
- `Category_Mapping_Validation_YYYYMMDD_HHMMSS.json` - Validation reports with timestamps
- `Category_Overhaul_Matrix_*.json` - Original matrix data for reference

## Integration

The validation system is automatically integrated into the main analysis flow in `seo_analyzer/services.py`. Every time a Category Overhaul Matrix analysis is run, the system will:

1. Generate the matrix as usual
2. Automatically run validation on the results
3. Save a validation report to `TEST RESULTS/`
4. Display accuracy statistics in the console

## Validation Logic

The validator determines if a category mapping is valid by:

1. **Extracting expected category** from the URL using the fixed URL parser
2. **Comparing expected vs actual** category mapping (exact string match)
3. **Identifying specific issues** if mappings don't match
4. **Generating detailed reports** with accuracy statistics

## Example Output

```json
{
  "validation_timestamp": "2025-08-26T17:26:00.192793",
  "total_rows_validated": 11,
  "summary": {
    "total_rows": 11,
    "correct_mappings": 11,
    "incorrect_mappings": 0,
    "accuracy_percentage": 100.0
  },
  "validation_results": [...]
}
```

## Testing

To test the validation system independently, you can create test scripts that import the validator and run it on sample data.
