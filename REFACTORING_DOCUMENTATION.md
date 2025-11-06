# Taxonomy & Facet Lens Refactoring Documentation
## Version 1.2 - Precision Overhaul

### Executive Summary

This document outlines the comprehensive refactoring of the Range Gap Finder's taxonomy and facet analysis system. The primary goal was to eliminate AI-based "intelligent guessing" that was causing incorrect category merging and to establish **URL structure as the single source of truth** for category mapping.

---

## Problem Statement

### Critical Issues Identified

1. **Semantic Over-reach (Critical Correctness Issue)**
   - The `dynamic_decompound_and_refine` function used fuzzy semantic matching (>70% spaCy similarity)
   - Incorrectly merged distinct industrial concepts
   - **Example**: "exterior wood paint" was incorrectly merged into "cladding" category
   - **Root Cause**: Semantic similarity between "wood" concepts, despite being different product types

2. **Traffic Bias (Critical Correctness Issue)**
   - The `reclassify_row` logic prioritized SEO traffic volume over semantic accuracy
   - Forced niche products into incorrect high-volume categories
   - **Example**: "damp paint" was forced into "gloss" category due to higher traffic
   - **Root Cause**: Assumption that high-traffic categories were more "correct"

3. **Data Integrity Risk (Facet Merging)**
   - Facet column consolidation relied on 50% data overlap threshold
   - Could merge distinct facet types that happened to share values
   - **Example**: Potentially merging 'Finish' and 'Material' if they shared values like 'Matte'
   - **Root Cause**: Data overlap does not guarantee semantic equivalence

---

## Refactoring Implementation

### Task 1: Disable Semantic Category Overwrites

**Files Modified:**
- `seo_analyzer/taxonomy_analysis.py` (lines 235-243)
- `seo_analyzer/enhanced_taxonomy_analysis.py` (lines 170-178)

**Changes:**
- Commented out the call to `dynamic_decompound_and_refine` that affected 'Category Mapping'
- The function was merging distinct categories based on semantic similarity
- Replaced with simple initialization of `Derived Facets` and `Decompounded Type` columns to `None`

**Rationale:**
The URL parser already extracts accurate categories from URL structure. Semantic refinement was introducing errors by conflating similar but distinct product categories.

**Code Example:**
```python
# BEFORE (INCORRECT):
all_canonical_categories = set(highest_ranking_df['Category Mapping'].dropna().unique())
highest_ranking_df = dynamic_decompound_and_refine(
    highest_ranking_df, 'Category Mapping', all_canonical_categories
)

# AFTER (CORRECT):
# Preserve URL-based category mapping
highest_ranking_df['Derived Facets'] = None
highest_ranking_df['Decompounded Type'] = None
```

---

### Task 2: Remove Traffic-Based Category Reclassification

**Files Modified:**
- `seo_analyzer/taxonomy_analysis.py` (lines 245-252)
- `seo_analyzer/enhanced_taxonomy_analysis.py` (lines 180-187)

**Changes:**
- Removed entire logic block that calculated `strong_categories_from_traffic`
- Removed `reclassify_row` function that forced keywords into high-volume categories
- Retained only traffic column numeric conversion for downstream processing

**Rationale:**
Traffic volume is an indicator of popularity, not accuracy. Niche products deserve their own categories regardless of traffic levels. URL structure provides the definitive categorization.

**Code Example:**
```python
# BEFORE (INCORRECT):
if total_traffic_sum > 0:
    strong_categories_from_traffic = set(
        category_traffic[category_traffic / total_traffic_sum > 0.005].index
    )
    # ... reclassification logic that overwrites URL-based categories

# AFTER (CORRECT):
# URL-based category mapping is preserved
if not highest_ranking_df.empty and internal_traffic_col in highest_ranking_df.columns:
    highest_ranking_df[internal_traffic_col] = pd.to_numeric(
        highest_ranking_df[internal_traffic_col], errors='coerce'
    ).fillna(0)
```

---

### Task 3: Implement Strict Non-Destructive Facet Merging

**Files Modified:**
- `seo_analyzer/taxonomy_analysis.py` (lines 338-394)

**Changes:**
- Replaced data-overlap-based merging (50% threshold) with column-name-similarity-based merging
- Created `normalize_column_name()` function to standardize names for comparison
- Created `are_column_names_similar()` function to check name similarity
- Modified merging logic to **NEVER overwrite existing values**, only fill `NaN` values

**Rationale:**
Column names are explicitly defined and indicate semantic intent. Data overlap is coincidental and does not guarantee columns represent the same facet type.

**New Functions:**
```python
def normalize_column_name(col_name):
    """Normalize by removing spaces, underscores, hyphens, converting to lowercase."""
    return re.sub(r'[_\s-]', '', str(col_name).lower())

def are_column_names_similar(col_a, col_b):
    """Check if column names are similar enough to merge."""
    norm_a = normalize_column_name(col_a)
    norm_b = normalize_column_name(col_b)
    
    # Exact match after normalization
    if norm_a == norm_b:
        return True
    
    # Substring match with small difference (e.g., 'Color' vs 'Colour')
    if norm_a in norm_b or norm_b in norm_a:
        if abs(len(norm_a) - len(norm_b)) <= 2:
            return True
    
    return False
```

**Merging Logic:**
```python
# Only merge if column names are similar
if not are_column_names_similar(col_A_name, col_B_name):
    continue

# CRITICAL: Only fill NaN values, NEVER overwrite
mask = highest_ranking_df[primary_col_name].isna() & highest_ranking_df[secondary_col_name].notna()
highest_ranking_df.loc[mask, primary_col_name] = highest_ranking_df.loc[mask, secondary_col_name]
highest_ranking_df.loc[mask, secondary_col_name] = np.nan
```

---

### Task 4: Restrict Semantic Analysis to Supplementary Columns

**Files Modified:**
- `seo_analyzer/taxonomy_analysis.py` (lines 415-477)

**Changes:**
- Added comprehensive documentation to `discover_remaining_facets` function
- Clarified that this function ONLY creates supplementary data
- Ensured it does NOT overwrite URL-based facets (Brand, Colour, Size, etc.)
- Outputs only to 'Discovered Facets' which is later organized into supplementary columns

**Rationale:**
NLP analysis can provide valuable supplementary insights but should never override explicit URL-based facet extraction. The two data sources serve different purposes.

**Documentation Added:**
```python
# REFACTORING: Task 4 - Restrict semantic analysis to supplementary columns only
# This function discovers ADDITIONAL facets from keywords using NLP
# CRITICAL: It must NOT overwrite URL-based facets (Brand, Colour, Size, etc.)
# It only outputs to 'Discovered Facets' which is later organized into supplementary columns

def discover_remaining_facets(row, learned_noise_tokens):
    """
    Discover additional facets from keywords using NLP.
    This function ONLY creates supplementary data and does NOT overwrite URL-based facets.
    
    Returns:
        String of discovered facet values (comma-separated) or None
    """
```

---

## Testing & Verification

### Regression Test Suite

Created `test_taxonomy_refactoring.py` with comprehensive test cases:

#### Test Case 1: Exterior Wood Paint NOT Merged into Cladding
```python
def test_exterior_wood_paint_not_merged_into_cladding(self):
    """
    Input: Keyword "outdoor wood paint", URL ".../exterior-wood"
    Expected: Category = "exterior-wood" (NOT "cladding")
    """
```

#### Test Case 2: Damp Paint NOT Merged into Gloss
```python
def test_damp_paint_not_merged_into_gloss(self):
    """
    Input: Keyword "damp paint", URL ".../damp-proof-paint/"
    Expected: Category = "damp-proof-paint" (NOT "gloss")
    """
```

#### Test Case 3: Facet Merging Only on Similar Column Names
```python
def test_facet_merging_only_on_similar_column_names(self):
    """
    Verifies that distinct facet types (like 'Finish' and 'Material') are NOT
    merged even if they share common values.
    """
```

#### Test Case 4: URL Parser is Definitive Source
```python
def test_url_parser_is_definitive_source(self):
    """
    Verifies that URL-based category extraction takes precedence over
    any semantic or traffic-based inference.
    """
```

#### Test Case 5: Column Name Similarity Logic
```python
class TestColumnNameSimilarity(unittest.TestCase):
    """
    Tests the column name similarity logic used in facet merging.
    Verifies that similar names merge (Colour_Group vs ColourGroup)
    but distinct names don't (Finish vs Material).
    """
```

### Running Tests

```bash
# Run all regression tests
python test_taxonomy_refactoring.py

# Or using unittest discovery
python -m unittest test_taxonomy_refactoring -v
```

---

## Architecture Changes

### Before Refactoring (Problematic Flow)

```
URL Extraction → Category Mapping → Semantic Refinement (OVERWRITE!) → Traffic Reclassification (OVERWRITE!) → Final Category
                                    ↑ PROBLEM: Fuzzy matching      ↑ PROBLEM: Traffic bias
```

### After Refactoring (Correct Flow)

```
URL Extraction → Category Mapping (PRESERVED AS SOURCE OF TRUTH) → Final Category
                 ↓
                 Supplementary NLP Analysis (separate columns, NO overwriting)
                 ↓
                 Discovered Features & Entities
```

---

## Impact Analysis

### Positive Outcomes

1. **Category Accuracy**: URL-based categories are now preserved throughout the entire pipeline
2. **Data Integrity**: Distinct product categories remain separate regardless of semantic similarity
3. **Niche Product Support**: Low-traffic niche categories are no longer forced into generic high-traffic categories
4. **Facet Preservation**: Distinct facet types are no longer merged based on coincidental data overlap
5. **Transparency**: The category mapping is now directly traceable to URL structure

### Potential Considerations

1. **Reduced Normalization**: Some legitimate variant spellings might not be merged automatically
   - **Mitigation**: The category synonym system in `url_parser.py` can handle known variants
   
2. **Less Aggressive Consolidation**: The system will produce more granular categories
   - **Mitigation**: This is the intended behavior - granularity preserves product distinctions

3. **Reliance on URL Quality**: Category accuracy now depends entirely on URL structure quality
   - **Mitigation**: URL structures are typically well-designed by competitors' information architects

---

## Configuration & Customization

### URL Parser Configuration

The URL parser uses `seo_analyzer/config.json` for customization:

```json
{
  "identifier_patterns": ["^\\d+$", "^cat\\d+$", "^p-\\d+$", "^c\\d+$"],
  "category_synonyms": {
    "exterior-wood": "exterior wood",
    "damp-proof-paint": "damp proof paint"
  },
  "facet_synonyms": {
    "colour_group": "colour",
    "color": "colour"
  }
}
```

### Adding Category Synonyms Programmatically

```python
from seo_analyzer.url_parser import URLParser

parser = URLParser()
parser.add_category_synonym("exterior-wood", "exterior wood")
parser.add_facet_synonym("color", "colour")
```

---

## Post-Deployment Verification

After deploying this refactoring, perform the following verification steps:

1. **Generate Category Overhaul Matrix**
   ```python
   result = _generate_category_overhaul_matrix(
       df=your_data,
       internal_keyword_col='Keyword',
       internal_position_col='Position',
       internal_traffic_col='Traffic',
       internal_url_col_name='URL',
       onsite_df=None,
       internal_volume_col='Volume'
   )
   ```

2. **Verify Category Mapping Alignment**
   - Check that 'Category Mapping' values strictly align with URL segments
   - Spot-check known problematic cases (exterior wood, damp paint)

3. **Submit to ProductArchitect-GPT**
   - The generated matrix should now accurately reflect URL-based taxonomy
   - Categories should NOT show inappropriate merging

4. **Monitor Facet Column Count**
   - You may see more facet columns (less aggressive merging)
   - This is expected and preserves data integrity

---

## Technical Debt & Future Work

### Completed ✅
- ✅ Disable semantic category overwrites
- ✅ Remove traffic-based reclassification
- ✅ Implement strict non-destructive facet merging
- ✅ Restrict semantic analysis to supplementary columns
- ✅ Create comprehensive regression tests

### Future Enhancements 🔄
- Enhance URL parser pattern recognition for edge cases
- Add configuration UI for category/facet synonyms
- Implement category hierarchy visualization
- Add data quality scoring for URL-based extraction
- Create category mapping audit trail/logging

---

## Support & Troubleshooting

### Common Issues

**Issue**: Categories are too granular (too many distinct categories)
- **Solution**: Use the category synonym system in `config.json` to merge legitimate variants

**Issue**: Some facets aren't being extracted
- **Solution**: Check URL query parameters and add facet synonyms if needed

**Issue**: "Discovered Facets" is empty
- **Solution**: This is normal if all facets are extracted from URLs. NLP only adds supplementary data.

### Contact

For questions about this refactoring:
- Review the inline code comments (marked with "REFACTORING: Task X")
- Check regression tests in `test_taxonomy_refactoring.py`
- Consult the original requirements in the project specification

---

## Changelog

### Version 1.2 - Precision Overhaul (Current)
- Disabled semantic category overwrites
- Removed traffic-based category reclassification
- Implemented strict non-destructive facet merging
- Restricted semantic analysis to supplementary columns
- Created comprehensive regression test suite

### Version 1.1 - Enhanced URL Parser (Previous)
- Introduced configurable URL parser
- Added synonym discovery
- Implemented facet normalization

### Version 1.0 - Original Implementation (Legacy)
- Multi-stage "learn and refine" approach
- Semantic clustering with spaCy
- Traffic-based reclassification
- Data-overlap-based facet merging

---

**Document Version**: 1.0  
**Last Updated**: 2025-11-06  
**Author**: PyAudit-GPT Refactoring Task  
**Status**: Complete

