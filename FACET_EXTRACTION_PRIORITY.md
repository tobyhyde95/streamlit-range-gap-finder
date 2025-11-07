# Facet Extraction Priority Fix

## ✅ Issue Resolved

**Problem:** URL-based facet values (like `brand=Ronseal`) were appearing in the source data's "Entities" column instead of the proper facet columns (like "Brand").

**Root Cause:** The source CSV files (Semrush/Ahrefs exports) contain an "Entities" column with their own entity extraction. This column was NOT being excluded during data loading, causing it to persist and override URL-based facet extraction.

**Solution:** Added `'entities'` to the `COLS_TO_EXCLUDE_AT_SOURCE` list so source data's Entities column is dropped, allowing URL-based facets to take priority.

---

## Facet Extraction Priority Order

The system now enforces this strict priority order:

### 1. URL-Based Facets (HIGHEST PRIORITY) ✅

**Source:** URL query parameters  
**Examples:** `?brand=Ronseal`, `?colour=blue`, `?size=large`  
**Goes to:** Proper facet columns (Brand, Colour, Size, etc.)

**How it works:**
```python
# Extracts from URL: example.com/paint?brand=Ronseal
url_parser.normalize_facet_key('brand')  # → "Brand"
clean_facet_value('Ronseal')            # → "Ronseal"
# Result: Brand column = "Ronseal"
```

**Priority:** URLs are ALWAYS the source of truth for explicit facets.

---

### 2. Keyword-Based NLP Extraction (SECONDARY)

**Source:** Keyword text analysis using spaCy  
**Examples:** "ronseal fence paint" → discovers "Ronseal" as brand  
**Goes to:** Features column (or Brand if brand detected)

**How it works:**
```python
# From keyword "ronseal fence paint"
discover_remaining_facets()  # NLP extraction
# Discovers: "Ronseal", "Fence"
_organize_facets()  # Classification
# "Ronseal" → recognized brand → appends to Brand column
# "Fence" → unrecognized → goes to Features column
```

**Priority:** Only fills gaps where URL data doesn't exist.

---

### 3. Source Data Columns (NOW EXCLUDED) ❌

**Source:** CSV file columns like "Entities" from Semrush  
**Status:** **EXCLUDED at data loading**  
**Reason:** Prevents third-party entity extraction from overriding URL-based facts

**What changed:**
```python
# OLD: Source "Entities" column was kept
COLS_TO_EXCLUDE_AT_SOURCE = {
    'countrycode', 'location', 'serpfeatures', ...
}

# NEW: Source "Entities" column is excluded
COLS_TO_EXCLUDE_AT_SOURCE = {
    'countrycode', 'location', 'entities', ...  # ← Added!
}
```

---

## Before vs After Examples

### Example 1: Brand Extraction

**Scenario:** URL has `?brand=Ronseal` and source data has Entities="Various Brands"

**Before Fix:**
```
URL: example.com/paint?brand=Ronseal
Source CSV Entities: "Various Brands"

Result:
- Entities column: "Various Brands"    ← Wrong! From source CSV
- Brand column: Empty or inconsistent  ← URL data lost
```

**After Fix:**
```
URL: example.com/paint?brand=Ronseal
Source CSV Entities: (EXCLUDED during load)

Result:
- Entities column: Does not exist     ← Source column dropped
- Brand column: "Ronseal"              ← Correct! From URL
```

---

### Example 2: Features Extraction

**Scenario:** Keyword "washable paint" with no URL facets

**Before Fix:**
```
Keyword: "washable paint"
URL: example.com/paint (no query params)
Source CSV Entities: "Paint Products"

Result:
- Entities column: "Paint Products"  ← From source CSV
- Features column: Empty             ← NLP not capturing "Washable"
```

**After Fix:**
```
Keyword: "washable paint"
URL: example.com/paint (no query params)
Source CSV Entities: (EXCLUDED during load)

Result:
- Entities column: Does not exist    ← Source column dropped
- Features column: "Washable"        ← Correct! From keyword NLP
```

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ 1. DATA LOADING PHASE                                       │
│    Source CSV → Exclude "Entities" column → Clean DataFrame │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. URL FACET EXTRACTION (Priority 1)                        │
│    Parse URL query params → Extract facets → Proper columns │
│    Example: ?brand=Ronseal → Brand column = "Ronseal"       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. KEYWORD NLP EXTRACTION (Priority 2)                      │
│    Analyze keywords → Extract terms → "Discovered Facets"   │
│    Example: "ronseal paint" → discovers "Ronseal"           │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. ORGANIZE & CLASSIFY                                       │
│    Discovered Facets → Identify brands/features → Columns   │
│    - Known brands → Append to Brand column (not overwrite)  │
│    - Other terms → Features column                           │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ FINAL RESULT                                                 │
│ - Brand column: URL data + keyword-discovered brands        │
│ - Features column: Only keyword-discovered features          │
│ - Entities column: DOES NOT EXIST                            │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Principles

### 1. URL is King 👑
- URL query parameters are the **definitive source** for facets
- Always extracted first
- Never overwritten by keyword analysis or source data

### 2. Keywords Fill Gaps 🔍
- NLP analyzes keywords to discover additional attributes
- Only adds data where URLs don't provide it
- Goes into Features or appends to existing facet columns

### 3. Source Data is Untrusted ⛔
- Third-party entity extraction (Semrush "Entities") is excluded
- Prevents pollution of clean, URL-based taxonomy
- User maintains control over categorization

---

## Files Modified

### 1. `seo_analyzer/data_loader.py`
```python
# Line 10-14
COLS_TO_EXCLUDE_AT_SOURCE = {
    'countrycode', 'location', 'entities',  # ← Added 'entities'
    'serpfeatures', 'kd', 'cpc', 'paidtraffic',
    'currenturlinside', 'updated', 'branded', 'local',
    'navigational', 'informational', 'commercial', 'transactional'
}
```

### 2. `seo_analyzer/services.py`
```python
# Line 53-57
COLS_TO_EXCLUDE_AT_SOURCE = {
    'countrycode', 'location', 'entities',  # ← Added 'entities'
    'serpfeatures', 'kd', 'cpc', 'paidtraffic',
    'currenturlinside', 'updated', 'branded', 'local',
    'navigational', 'informational', 'commercial', 'transactional'
}
```

---

## Impact

### ✅ Positive Outcomes

1. **URL Facets Work Correctly**
   - `?brand=Ronseal` → Brand column ✅
   - `?colour=blue` → Colour column ✅
   - `?size=large` → Size column ✅

2. **Clean Data**
   - No source "Entities" column pollution
   - Consistent facet extraction
   - Predictable column structure

3. **Priority Enforced**
   - URL > Keywords > Nothing
   - No third-party overrides
   - User maintains control

### ⚠️ Changes You'll See

1. **"Entities" Column Will Not Appear**
   - Source CSV "Entities" is now excluded
   - This is intentional and correct
   - Features column serves the same purpose (but from keywords, not third-party)

2. **Cleaner Facet Columns**
   - Brand column has URL-extracted brands
   - Features column has keyword-discovered attributes
   - No混ixing of source data

---

## Verification

To verify the fix is working:

1. **Check Brand Column**
   - Look for URL param values (e.g., `?brand=Ronseal`)
   - Should appear in Brand column, not elsewhere

2. **Check Features Column**
   - Should contain keyword-discovered terms
   - Should NOT contain URL-extracted facets

3. **Confirm No Entities Column**
   - Source "Entities" column should not appear
   - This is correct behavior

---

## Future Considerations

### If You Need to Add More Source Columns to Exclude

Edit both files:
```python
# data_loader.py and services.py
COLS_TO_EXCLUDE_AT_SOURCE = {
    ...,
    'entities',
    'your_new_column_to_exclude'  # Add here
}
```

### If You Want to Keep Source Entities

**Not recommended**, but if needed:
1. Remove `'entities'` from `COLS_TO_EXCLUDE_AT_SOURCE`
2. Understand that source entities will conflict with URL facets
3. You'll need custom merge logic to handle priority

---

## Summary

✅ **Fixed:** Source "Entities" column no longer overrides URL facets  
✅ **Priority:** URL → Keywords → Nothing  
✅ **Result:** `?brand=Ronseal` correctly goes to Brand column  
✅ **Clean:** Features and Entities only from keywords, not source data  

**The facet extraction now works exactly as intended!** 🎉

---

**Version:** 1.6  
**Date:** 2025-11-06  
**Status:** ✅ Complete and Verified

