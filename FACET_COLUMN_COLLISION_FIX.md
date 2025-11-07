# Facet Column Collision Fix

## Issue Identified

**Problem:** URL facet parameters like `volume=9_ltr` were not appearing in the Category Overhaul Matrix, even though the extraction logic was working correctly.

**Example URL:**
```
https://www.screwfix.com/c/painting-decorating/fence-paint/cat850566?brand=ronseal&volume=9_ltr
```

Only `brand=Ronseal` was appearing in the matrix, while `volume=9_ltr` was missing.

## Root Cause

The issue was caused by **column name collision** between:
1. **Source data column:** "Volume" (search volume from Semrush/Ahrefs - numeric data like 200, 150, etc.)
2. **Facet column:** "volume" from URL parameters (product volume like "9_ltr", "10_ltr") which gets normalized to "Volume" after title case conversion

When both DataFrames were concatenated:
```python
highest_ranking_df = pd.concat([highest_ranking_df, explicit_facets_df], axis=1)
```

This created duplicate "Volume" columns. The subsequent duplicate handling logic would merge them using:
```python
if highest_ranking_df.columns.has_duplicates:
    highest_ranking_df = highest_ranking_df.groupby(level=0, axis=1).apply(...)
```

This caused the **facet data to be lost** because the groupby operation would take the first column (numeric search volume) and drop the second column (product volume facet).

## Solution Implemented

Added column collision detection and automatic renaming **before concatenation**:

```python
# Check for column name collisions with existing DataFrame columns
existing_cols = set(highest_ranking_df.columns)
facet_rename_map = {}
for col in explicit_facets_df.columns:
    if col in existing_cols:
        # Rename facet column to avoid collision
        new_col_name = f"Product {col}" if col in ['Volume', 'Size', 'Weight', 'Capacity'] else f"{col} Facet"
        print(f"⚠️  Column collision detected: '{col}' already exists. Renaming facet column to '{new_col_name}'")
        facet_rename_map[col] = new_col_name

if facet_rename_map:
    explicit_facets_df = explicit_facets_df.rename(columns=facet_rename_map)
```

### Renaming Logic

The fix applies intelligent renaming:
- **Physical attributes** (Volume, Size, Weight, Capacity) → Prefixed with "Product"
  - `Volume` → `Product Volume`
  - `Size` → `Product Size`
  - `Weight` → `Product Weight`
  - `Capacity` → `Product Capacity`
  
- **Other facets** → Suffixed with "Facet"
  - `Color` → `Color Facet` (if it collided with an existing "Color" column)

## Files Modified

1. **`seo_analyzer/taxonomy_analysis.py`** (lines 298-317)
   - Added collision detection and renaming logic in `_generate_category_overhaul_matrix()`
   
2. **`seo_analyzer/enhanced_taxonomy_analysis.py`** (lines 229-248)
   - Added collision detection and renaming logic in `_generate_enhanced_category_overhaul_matrix()`

## Results

### Before Fix
```
Columns: ['Keyword', 'Volume', 'Source', 'Brand', 'Volume', 'Colour']  # Duplicate Volume!
Data: Only one Volume column appears, containing search volume (200, 150, ...)
Product volume facet (9 Ltr, 10 Ltr) is LOST
```

### After Fix
```
Columns: ['Keyword', 'Volume', 'Source', 'Brand', 'Product Volume', 'Colour']
Data: 
  - Volume column: Search volume (200, 150, ...)
  - Product Volume column: Facet values (9 Ltr, 10 Ltr, ...)
All data is PRESERVED
```

## Testing

The fix was thoroughly tested with real Screwfix URLs containing multiple facets:
- ✅ `brand=ronseal&volume=9_ltr` → Both Brand and Product Volume extracted
- ✅ `volume=10_ltr` → Product Volume extracted
- ✅ `colour=magnolia&volume=10_ltr` → Both Colour and Product Volume extracted
- ✅ No duplicate columns
- ✅ Search volume data preserved
- ✅ All facet data preserved

## Impact

This fix ensures that:
1. **All URL facets are correctly extracted** into their own columns
2. **No data loss** occurs during concatenation
3. **Clear column naming** distinguishes between source data columns and facet columns
4. **Backward compatibility** is maintained for data without collisions
5. **User visibility** through warning messages when collisions are detected

## Future Considerations

If additional common column name collisions are identified, they can be added to the smart renaming logic:
```python
if col in ['Volume', 'Size', 'Weight', 'Capacity', 'NewCollisionName']:
    new_col_name = f"Product {col}"
```

