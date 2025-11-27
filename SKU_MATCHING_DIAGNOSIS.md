# SKU Matching Diagnosis & Solution Guide

## Problem Summary

SKU matching is failing for categories like "Anti Climb Paint" and "Masonry Paint", even though:
- The categories exist in the Category Overhaul Matrix (confirmed by your JSON export)
- The matching logic works correctly (confirmed by test script)
- SKUs contain the expected text

## Root Cause Analysis

### Issue 1: Frontend Category-Facet Map Construction
The frontend's `buildCategoryFacetPairs` function is not finding "Anti Climb Paint" in the Category Mapping field. Instead, it's seeing:
- `Category Mapping: "Paint.Cat"` (generic category)
- `Navigation_Type: "Anti Climb"` (specific category)

This suggests the Category Overhaul Matrix data may have been:
- Aggregated/merged, causing specific categories to be lost
- Transformed, with category names moved to facet fields
- Filtered, removing rows with specific categories

### Issue 2: Data Structure Mismatch
Your JSON export shows `Category Mapping: "Anti Climb Paint"`, but the frontend sees `Category Mapping: "Paint.Cat"`. This indicates a data transformation issue.

## Diagnostic Tools Created

### 1. `test_sku_matching.py`
Comprehensive test suite that validates:
- Normalization (hyphens, underscores, spaces)
- Token extraction
- Token matching
- Full SKU matching end-to-end

**Run it:**
```bash
python3 test_sku_matching.py
```

### 2. `diagnose_pim_issue.py`
Diagnostic tool that analyzes:
- What categories are in the category-facet map
- What SKU data is being processed
- Why specific matches are failing

**Run it:**
```bash
python3 diagnose_pim_issue.py <pim_csv_path> [category_map.json]
```

## Immediate Next Steps

### Step 1: Check Frontend Console
1. Refresh your browser
2. Open browser console (F12)
3. Run PIM analysis
4. Look for `[DEBUG FRONTEND]` messages
5. Check:
   - What categories are found with "climb"
   - What the Category Mapping values actually are
   - Whether Navigation_Type contains the category name

### Step 2: Export Category-Facet Map
1. After running PIM analysis, check the exported results
2. Export the category-facet map as JSON
3. Run the diagnostic tool:
   ```bash
   python3 diagnose_pim_issue.py your_pim_data.csv exported_category_map.json
   ```

### Step 3: Verify Category Overhaul Matrix
1. In your Category Overhaul Matrix view, search for "Anti Climb Paint"
2. Check what the `Category Mapping` field contains
3. Check if there are multiple rows (one per facet combination)
4. Verify if the category name is in a different field

## Potential Solutions

### Solution A: Fix Category Name Construction
If categories are split across fields (e.g., "Paint.Cat" + "Anti Climb" in Navigation_Type), we may need to construct the full category name by combining fields.

### Solution B: Fix Data Aggregation
If the Category Overhaul Matrix has been over-aggregated, we may need to:
- Use the raw matrix data before aggregation
- Or reconstruct categories from facet combinations

### Solution C: Fix Frontend Data Processing
If the data is being transformed incorrectly, we may need to:
- Check `applyOverridesAndMerge` function
- Check `transformDataForTimeframe` function
- Ensure category names are preserved during transformation

## Testing Checklist

- [ ] Run `test_sku_matching.py` - all tests should pass
- [ ] Check browser console for debug output
- [ ] Export category-facet map and verify categories
- [ ] Run `diagnose_pim_issue.py` with your actual data
- [ ] Verify Category Overhaul Matrix contains expected categories
- [ ] Check if category names are in different fields

## Expected Results

After fixes, you should see:
- "Anti Climb Paint" in the category-facet map
- SKU 74796 matching "Anti Climb Paint"
- "Masonry Paint" matching SKUs with "Masonry" in product name
- All categories from your Category Overhaul Matrix included

## Debug Output to Share

When reporting issues, please share:
1. Browser console output (all `[DEBUG FRONTEND]` messages)
2. Backend terminal output (all `[DEBUG]` messages)
3. Results from `diagnose_pim_issue.py`
4. Sample of your Category Overhaul Matrix data (first few rows with "Anti Climb Paint")

