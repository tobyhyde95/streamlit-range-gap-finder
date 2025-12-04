# Smart SKU Counting - Quick Start Guide

## What Changed?

The Taxonomy Analysis lens now includes **Smart SKU Counting** and **Classification Logic** to provide accurate SKU counts and intelligent site hierarchy recommendations.

---

## New Features at a Glance

### 1. Smart SKU Counting
- **Eliminates false positives** (e.g., "Spray Paint" no longer matches "Masonry Paint with spray applicator")
- **Self-calibrating** - Automatically detects generic vs. specific terms
- **Weighted scoring** - Prioritizes product names over marketing copy

### 2. Classification Recommendations
- **Core Category** - Terms with ≥40 SKUs (sufficient product depth)
- **SEO Landing Page** - Terms with <40 SKUs but ≥1000 monthly traffic (high demand)
- **Facet / Filter** - Terms with <40 SKUs and <1000 traffic (best as filters)

### 3. Enhanced Excel Export
- New columns: `Calculated SKU Count` and `Recommendation`
- Sorted by Monthly Organic Traffic (highest first)
- Appears in Category Consolidation sheet

---

## How It Works (Simple Explanation)

### Column Importance Levels

The system assigns different importance to different columns:

| Column Type | Points | Examples |
|-------------|--------|----------|
| **Product Name** | 10 pts | Part Name, Product Name |
| **Attributes** | 5 pts | Brand, Finish, Colour, Material |
| **Descriptions** | 1 pt | Web Copy, Catalogue Copy |
| **Ignored** | 0 pts | Product Code, SKU ID |

### Noise Detection

The system scans description columns:
- If a term appears in >15% of descriptions → **NOISY** (generic term like "spray", "white")
- If a term appears in ≤15% of descriptions → **SPECIFIC** (specialized term like "anti mould")

### Match Thresholds

- **Noisy terms**: Need 5+ points to match (must be in product name or attributes)
- **Specific terms**: Need 1+ point to match (can be in descriptions)

---

## Example Scenarios

### Scenario 1: Searching for "Spray Paint"

**Term is NOISY** (appears in 80% of descriptions)  
**Threshold: 5 points**

| SKU | Part Name | Description | Score | Match? |
|-----|-----------|-------------|-------|--------|
| SKU001 | **Spray Paint** 400ml | Professional spray paint | 10 pts | ✓ YES |
| SKU002 | Masonry Paint 10L | Paint with **spray** applicator | 0 pts | ✗ NO |
| SKU003 | Wood Paint 5L | Can be applied via **spray** | 0 pts | ✗ NO |

**Result**: Only 1 SKU matches (SKU001) ✓ Accurate!

### Scenario 2: Searching for "Anti Mould"

**Term is SPECIFIC** (appears in 5% of descriptions)  
**Threshold: 1 point**

| SKU | Part Name | Description | Score | Match? |
|-----|-----------|-------------|-------|--------|
| SKU001 | **Anti Mould Paint** 5L | Premium **anti mould** paint | 11 pts | ✓ YES |
| SKU002 | Bathroom Paint 2.5L | Prevents **mould** growth | 1 pt | ✓ YES |
| SKU003 | Masonry Paint 10L | Durable exterior paint | 0 pts | ✗ NO |

**Result**: 2 SKUs match (SKU001, SKU002) ✓ Accurate!

---

## Classification Examples

### Example 1: "Paint" (250 SKUs, 5000 traffic)
→ **Core Category**  
*Reasoning: 250 ≥ 40 SKUs - sufficient product depth for a main category*

### Example 2: "Anti Mould Paint" (15 SKUs, 2500 traffic)
→ **SEO Landing Page**  
*Reasoning: 15 < 40 SKUs but 2500 ≥ 1000 traffic - create targeted landing page*

### Example 3: "Low VOC" (8 SKUs, 300 traffic)
→ **Facet / Filter**  
*Reasoning: 8 < 40 SKUs and 300 < 1000 traffic - best as a filterable attribute*

---

## Using the New Features

### In the Taxonomy Analysis Lens

1. **Upload your data** as usual (Our Data, Competitor Data, Onsite Search)
2. **Run the analysis** - The Category Overhaul Matrix is generated
3. **View the results** - Two new columns appear:
   - `Calculated SKU Count` - Shows how many SKUs match each term
   - `Recommendation` - Shows the classification (Category / Landing Page / Facet)
4. **Export to Excel** - The Category Consolidation sheet includes these columns

### In the Excel Export

Open the **Category Consolidation** sheet:
- Categories are sorted by traffic (highest first)
- Look at the `Recommendation` column for guidance
- Use `Calculated SKU Count` to validate product depth

---

## Adjusting Thresholds (Advanced)

If you need to customize the thresholds, edit `seo_analyzer/pim_sku_analyzer.py`:

```python
# Line ~60-61
SKU_THRESHOLD_HIGH = 40          # Change to 50 for stricter Core Category requirement
TRAFFIC_THRESHOLD_HIGH = 1000    # Change to 1500 for stricter Landing Page requirement

# Line ~92
NOISE_FREQUENCY_THRESHOLD = 0.15  # Change to 0.20 for more lenient noise detection
```

---

## Troubleshooting

### "Calculated SKU Count shows None"

**Cause**: PIM data hasn't been uploaded yet  
**Solution**: Upload a PIM CSV file in the PIM SKU Mapping section first

### "Term is classified as NOISY but seems specific"

**Cause**: The term appears in >15% of product descriptions  
**Solution**: This is correct behavior - the term is genuinely common in your catalog

### "SKU count seems too low"

**Cause**: The term might be noisy and only matches products where it appears in the name/attributes  
**Solution**: Check the noise detection output in the console logs

---

## Technical Details

### Files Modified

- `seo_analyzer/pim_sku_analyzer.py` - Core logic
- `seo_analyzer/taxonomy_analysis.py` - Integration
- `assets/js/app.js` - Excel export

### API Functions

```python
# Calculate SKU counts for multiple terms
from seo_analyzer.pim_sku_analyzer import calculate_sku_counts_for_terms

sku_counts = calculate_sku_counts_for_terms(
    pim_csv_path='path/to/pim.csv',
    terms=['Anti Mould Paint', 'Spray Paint', ...],
    sku_id_column='TS Product Code'
)

# Classify a term
from seo_analyzer.pim_sku_analyzer import classify_term_by_depth_and_demand

recommendation = classify_term_by_depth_and_demand(
    sku_count=15,
    organic_traffic=2500
)
# Returns: "SEO Landing Page"
```

---

## Testing

Run the test suite to validate the implementation:

```bash
cd /Users/tobyhyde/Documents/ai_applications_python/range_gap_finder
python3 test_smart_sku_counting.py
```

Expected output:
```
✓ ALL TESTS PASSED
```

---

## Support

For questions or issues:
1. Check the full documentation: `SMART_SKU_COUNTING_REFACTOR.md`
2. Review the test cases: `test_smart_sku_counting.py`
3. Check console logs for noise detection output

---

## Summary

✅ **More accurate** - Eliminates false positives  
✅ **Intelligent** - Provides site hierarchy recommendations  
✅ **Automatic** - No manual configuration needed  
✅ **Tested** - Comprehensive test suite included  

The Smart SKU Counting system is ready to use!

