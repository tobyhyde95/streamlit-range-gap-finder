# Smart SKU Counting & Classification Logic - Implementation Summary

## Overview

This document describes the implementation of **Smart SKU Counting** and **Depth vs. Demand Classification** for the Taxonomy Analysis lens. These features eliminate false positives in SKU matching and provide intelligent recommendations for site hierarchy.

---

## Part 1: Smart SKU Counting Logic

### Problem Statement

The previous implementation used simple text matching to count SKUs, leading to **false positives**. For example:
- Searching for "Spray Paint" would incorrectly match a "Masonry Paint" product that merely mentions "spray application" in its description.
- Generic terms like "white" or "paint" would match thousands of irrelevant products.

### Solution: Weighted Scoring with Dynamic Noise Detection

The new system uses a **three-tier approach**:

1. **Column Weighting** - Different columns have different confidence levels
2. **Noise Detection** - Automatically identifies generic vs. specific terms
3. **Dynamic Thresholding** - Adjusts match requirements based on term specificity

---

## Column Weight Configuration

### Weight Tiers

| Tier | Weight | Column Types | Examples |
|------|--------|--------------|----------|
| **High Confidence** | 10 pts | Definitive product identifiers | Part Name, Part Name Type, Product Name |
| **Medium Confidence** | 5 pts | Brand and dynamic attributes | Product Brand Name, Finish, Substrate, Application Method |
| **Low Confidence** | 1 pt | Marketing copy and descriptions | Toolstation Web Copy, Catalogue Copy, Supplier Copy |
| **Ignore** | 0 pts | System identifiers | TS Product Code, SKU ID |

### Implementation

```python
# High confidence columns (definitive match)
HIGH_CONFIDENCE_COLUMNS = [
    'part name', 'part_name', 'partname',
    'part name type', 'part_name_type', 'partnametype',
    'product name', 'product_name', 'productname'
]

# Low confidence columns (description/copy)
LOW_CONFIDENCE_COLUMNS = [
    'toolstation web copy', 'web copy', 'webcopy',
    'toolstation catalogue copy', 'catalogue copy', 'cataloguecopy',
    'supplier copy', 'suppliercopy',
    'description', 'desc', 'long description', 'short description'
]

# Ignored columns
IGNORE_COLUMNS = [
    'ts product code', 'product code', 'productcode',
    'sku', 'sku_id', 'id', 'code'
]
```

**Dynamic Column Handling**: Any column not explicitly listed is assigned **Medium Confidence (5 pts)**, allowing the system to handle variable CSV structures.

---

## Noise Detection Algorithm

### Threshold

**15% Frequency Threshold**: If a term appears in description columns of more than 15% of rows, it's classified as "noisy."

### Logic Flow

```python
def _is_term_noisy(pim_df, term, description_columns):
    """
    Scan description columns only.
    If term appears in > 15% of rows, return True (noisy).
    Otherwise, return False (specific).
    """
    total_rows = len(pim_df)
    matching_rows = count_rows_with_term_in_descriptions(pim_df, term, description_columns)
    frequency = matching_rows / total_rows
    
    return frequency > 0.15  # 15% threshold
```

### Examples

| Term | Frequency | Classification | Reasoning |
|------|-----------|----------------|-----------|
| "spray" | 80% | **NOISY** | Generic term appearing in many product descriptions |
| "white" | 65% | **NOISY** | Common color mentioned across categories |
| "anti mould" | 5% | **SPECIFIC** | Specialized feature for specific products |
| "low voc" | 2% | **SPECIFIC** | Technical specification for niche products |

---

## Dynamic Thresholding

### Match Threshold Rules

| Term Type | Threshold | Behavior |
|-----------|-----------|----------|
| **Noisy** (>15% frequency) | 5 points | Must appear in Part Name, Brand, or Attributes. Description matches are **ignored**. |
| **Specific** (≤15% frequency) | 1 point | A mention in any column (including descriptions) is sufficient. |

### Scoring Example

**Scenario**: Searching for "Spray Paint"

**SKU 1: Spray Paint 400ml Red**
- Part Name: "Spray Paint 400ml Red" → **10 pts** ✓
- Description: "Professional spray paint for all surfaces" → **0 pts** (ignored, term is noisy)
- **Total: 10 pts ≥ 5** → **MATCH** ✓

**SKU 2: Masonry Paint 10L**
- Part Name: "Masonry Paint 10L" → **0 pts**
- Description: "Durable paint with spray application option" → **0 pts** (ignored, term is noisy)
- **Total: 0 pts < 5** → **NO MATCH** ✓

**SKU 3: Anti Mould Paint 5L** (searching for "Anti Mould")
- Part Name: "Anti Mould Paint 5L" → **10 pts** ✓
- Description: "Premium anti mould paint for bathrooms" → **1 pt** (term is specific)
- **Total: 11 pts ≥ 1** → **MATCH** ✓

---

## Part 2: Classification Logic (Depth vs. Demand)

### Classification Matrix

The system recommends whether a term should be a **Category**, **SEO Landing Page**, or **Facet** based on two dimensions:

1. **Depth** (SKU Count) - How many products match this term?
2. **Demand** (Organic Traffic) - How much search interest exists?

### Thresholds

```python
SKU_THRESHOLD_HIGH = 40
TRAFFIC_THRESHOLD_HIGH = 1000
```

### Decision Rules

| SKU Count | Organic Traffic | Recommendation | Reasoning |
|-----------|-----------------|----------------|-----------|
| ≥ 40 | Any | **Core Category** | Sufficient product depth to warrant a dedicated category page |
| < 40 | ≥ 1000 | **SEO Landing Page** | High demand but limited products - create a virtual category/landing page |
| < 40 | < 1000 | **Facet / Filter** | Low depth and demand - best served as a filterable attribute |

### Examples

| Term | SKU Count | Traffic | Recommendation | Explanation |
|------|-----------|---------|----------------|-------------|
| "Paint" | 250 | 5000 | **Core Category** | Large product range justifies main category |
| "Anti Mould Paint" | 15 | 2500 | **SEO Landing Page** | High search volume but limited products - create targeted landing page |
| "Low VOC" | 8 | 300 | **Facet / Filter** | Niche specification - better as a filter option |
| "Exterior Wood Paint" | 45 | 1200 | **Core Category** | Sufficient products to create dedicated category |

### Implementation

```python
def classify_term_by_depth_and_demand(sku_count, organic_traffic):
    if sku_count >= SKU_THRESHOLD_HIGH:
        return "Core Category"
    elif organic_traffic >= TRAFFIC_THRESHOLD_HIGH:
        return "SEO Landing Page"
    else:
        return "Facet / Filter"
```

---

## Part 3: Excel Export Integration

### New Columns in Category Consolidation Sheet

The Excel export now includes two new columns:

1. **Calculated SKU Count** - The result of Smart SKU Counting logic
2. **Recommendation** - The classification result (Core Category / SEO Landing Page / Facet)

### Column Placement

These columns appear in the **metrics section** (after traffic/search columns, before facet columns):

```
| Category Mapping | Monthly Traffic | Total Searches | Calculated SKU Count | Recommendation | Brand | Colour | ... |
```

### Sorting

The export is **sorted by Monthly Organic Traffic (descending)** so high-impact items appear at the top.

---

## Integration Points

### Files Modified

1. **`seo_analyzer/pim_sku_analyzer.py`**
   - Added column weight configuration constants
   - Implemented `_get_column_weight()` function
   - Implemented `_is_term_noisy()` function
   - Implemented `calculate_match_score_weighted()` function
   - Implemented `_calculate_sku_count_for_term_weighted()` function
   - Added `calculate_sku_counts_for_terms()` public API
   - Added `classify_term_by_depth_and_demand()` function

2. **`seo_analyzer/taxonomy_analysis.py`**
   - Imported classification function
   - Added `Calculated SKU Count` and `Recommendation` columns to matrix output
   - Applied classification logic when SKU counts are available
   - Added sorting by Monthly Organic Traffic (descending)

3. **`assets/js/app.js`**
   - Updated `excludedColumns` list to include new columns
   - Updated `metricColumns` list to include new columns
   - Modified aggregation logic to handle non-numeric columns properly

---

## Usage Example

### For PIM SKU Analysis (Existing Flow)

The existing PIM analysis flow continues to work as before. The Smart SKU Counting logic is available as an alternative approach.

### For Taxonomy Analysis (New Flow)

When a PIM file is available, the taxonomy analysis can now calculate SKU counts:

```python
from seo_analyzer.pim_sku_analyzer import calculate_sku_counts_for_terms

# Extract terms from Category Overhaul Matrix
terms = ['Anti Mould Paint', 'Spray Paint', 'Low VOC Paint', ...]

# Calculate SKU counts using Smart SKU Counting
sku_counts = calculate_sku_counts_for_terms(
    pim_csv_path='path/to/pim_export.csv',
    terms=terms,
    sku_id_column='TS Product Code'
)

# Results: {'Anti Mould Paint': 15, 'Spray Paint': 42, 'Low VOC Paint': 8, ...}
```

The classification is then automatically applied in `taxonomy_analysis.py`.

---

## Testing

### Test Suite

A comprehensive test suite is provided in `test_smart_sku_counting.py`:

```bash
python3 test_smart_sku_counting.py
```

### Test Coverage

1. ✓ Column weight assignment
2. ✓ Noise detection algorithm
3. ✓ Weighted match scoring
4. ✓ Classification logic
5. ✓ End-to-end SKU counting

All tests pass successfully.

---

## Performance Considerations

### Vectorized Operations

The noise detection uses pandas vectorized operations for efficiency:

```python
# Efficient: Vectorized string matching
matches = pim_df[col].astype(str).str.lower().str.contains(term, na=False)
```

### Pre-computation

Column weights are computed once per analysis, not per row:

```python
column_weights_map = {col: _get_column_weight(col) for col in all_columns}
```

### Caching

The noise detection result is cached per term, avoiding redundant scans.

---

## Future Enhancements

### Potential Improvements

1. **Machine Learning** - Train a model to learn optimal weights from historical data
2. **Synonym Handling** - Recognize "colour" vs "color", "grey" vs "gray"
3. **Fuzzy Matching** - Handle typos and variations (e.g., "anti-mould" vs "antimould")
4. **Custom Thresholds** - Allow users to configure the 15% noise threshold and 40/1000 classification thresholds
5. **Batch Processing** - Optimize for processing thousands of terms at once

---

## Constraints & Guardrails

### Scope Limitation

✓ **Affects**: Taxonomy Analysis lens only  
✗ **Does NOT affect**: Competitor Gap Analysis, Market Share Analysis, or other modules

### Data Flexibility

✓ **Handles**: Variable CSV structures with inconsistent headers  
✓ **Handles**: Missing columns gracefully  
✓ **Handles**: Exotic character encodings (UTF-8, CP1252, Latin-1)

### Backward Compatibility

✓ **Preserves**: Existing PIM SKU analysis functionality  
✓ **Preserves**: All existing API endpoints  
✓ **Adds**: New optional functionality without breaking changes

---

## Configuration Reference

### Constants (Top of `pim_sku_analyzer.py`)

```python
# Classification thresholds
SKU_THRESHOLD_HIGH = 40          # SKUs required for "Core Category"
TRAFFIC_THRESHOLD_HIGH = 1000    # Traffic required for "SEO Landing Page"

# Column weights
COLUMN_WEIGHTS = {
    'high_confidence': 10,
    'medium_confidence': 5,
    'low_confidence': 1,
    'ignore': 0
}

# Noise detection
NOISE_FREQUENCY_THRESHOLD = 0.15  # 15% threshold
```

To adjust thresholds, modify these constants at the top of the file.

---

## Summary

The Smart SKU Counting refactor delivers:

✅ **Accurate SKU matching** - Eliminates false positives through weighted scoring  
✅ **Intelligent classification** - Recommends optimal site hierarchy based on depth and demand  
✅ **Self-calibrating** - Automatically adapts to noisy vs. specific terms  
✅ **Flexible** - Handles variable CSV structures  
✅ **Performant** - Uses vectorized operations for speed  
✅ **Well-tested** - Comprehensive test suite with 100% pass rate  
✅ **Documented** - Clear documentation and examples  

The system is now production-ready for the Taxonomy Analysis lens.

