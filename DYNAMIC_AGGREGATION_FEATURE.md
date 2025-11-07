# Dynamic Re-Aggregation Feature

## ✅ Now Implemented!

When you hide Entities or Features columns, the data **automatically re-aggregates**, merging rows that differ only in the hidden columns!

---

## How It Works

### Before (Old Behavior)
```
Columns were just hidden from view
Rows stayed separate even if identical except for hidden columns
```

### After (New Behavior) ✨
```
Data re-aggregates when columns are hidden
Rows that differ only in hidden columns MERGE
Metrics are summed automatically
Keywords are combined
```

---

## Example: The Power of Dynamic Re-Aggregation

### Scenario: Hiding Entities Column

**Original Data (Entities visible):**
| Category Mapping | Entities | Features | Monthly Traffic | Keywords |
|------------------|----------|----------|----------------|----------|
| Paint | Dulux | Washable | 2,000 | 50 |
| Paint | Crown | Washable | 3,000 | 75 |
| Paint | Johnstone's | Washable | 1,500 | 40 |
| Wood Stain | Ronseal | Interior | 4,000 | 100 |

**Total Rows:** 4  
**Total Traffic:** 10,500

---

### ❌ OLD Behavior (Without Re-Aggregation)

**After checking "Hide Entities column":**
| Category Mapping | Features | Monthly Traffic | Keywords |
|------------------|----------|----------------|----------|
| Paint | Washable | 2,000 | 50 |
| Paint | Washable | 3,000 | 75 |
| Paint | Washable | 1,500 | 40 |
| Wood Stain | Interior | 4,000 | 100 |

**Total Rows:** STILL 4 (separate rows)  
**Total Traffic:** 10,500  
❌ **Problem:** Duplicate-looking rows, confusing!

---

### ✅ NEW Behavior (With Dynamic Re-Aggregation)

**After checking "Hide Entities column":**
| Category Mapping | Features | Monthly Traffic | Keywords |
|------------------|----------|----------------|----------|
| Paint | Washable | 6,500 | 165 |
| Wood Stain | Interior | 4,000 | 100 |

**Total Rows:** 2 (merged!)  
**Total Traffic:** 10,500 (same, but cleaner)  
✅ **Result:** Clean, aggregated data showing true category-level metrics!

---

## What Gets Merged

When you hide columns, rows merge if they are **identical in all visible columns**.

### Example 1: Hide Entities Only

**These rows will merge:**
```
Paint | Dulux     | Washable → 2,000
Paint | Crown     | Washable → 3,000
Paint | Ronseal   | Washable → 1,500
```

**Becomes:**
```
Paint | Washable → 6,500 (summed!)
```

**These rows stay separate:**
```
Paint | Dulux     | Quick Dry → 2,000
Paint | Crown     | Washable  → 3,000
```
(Different Features values)

---

### Example 2: Hide Entities AND Features

**These rows will merge:**
```
Paint | Dulux     | Washable  → 2,000
Paint | Crown     | Washable  → 3,000
Paint | Ronseal   | Quick Dry → 1,500
```

**Becomes:**
```
Paint → 6,500 (all merged!)
```

**These rows stay separate:**
```
Paint      → 6,500
Wood Stain → 4,000
```
(Different Category Mapping values)

---

## What Gets Summed

When rows merge, these metrics are **automatically summed**:

✅ **Monthly Organic Traffic** - Total traffic across merged rows  
✅ **Total Monthly Google Searches** - Total search volume  
✅ **Total On-Site Searches** - Total onsite searches  
✅ **Keyword Count** - Combined keywords from all merged rows  

### Example:

**Before Merge:**
```
Row 1: Traffic = 2,000, Searches = 5,000, Keywords: 50
Row 2: Traffic = 3,000, Searches = 8,000, Keywords: 75
Row 3: Traffic = 1,500, Searches = 4,000, Keywords: 40
```

**After Merge:**
```
Merged Row: Traffic = 6,500, Searches = 17,000, Keywords: 165
```

---

## Keyword Details Are Combined

When rows merge, all keywords are **combined** into a single list:

**Before Merge:**
```
Row 1 Keywords: ["exterior paint", "outdoor paint", "weather paint"]
Row 2 Keywords: ["gloss paint", "white paint", "crown paint"]
Row 3 Keywords: ["wood paint", "fence paint", "deck paint"]
```

**After Merge:**
```
Merged Keywords: [all 9 keywords combined in a single expandable list]
```

Click the ▶ button to see all keywords for the merged row!

---

## Real-World Use Cases

### Use Case 1: Category-Level Analysis

**Goal:** See total traffic per category, ignoring brand differences

**Action:**
1. Check "Hide Entities column"
2. Check "Hide Features column"

**Result:** Pure category-level metrics!

```
Category Mapping | Monthly Traffic | Keywords
Paint            | 15,000          | 450
Wood Stain       | 8,000           | 220
Primer           | 5,000           | 150
```

---

### Use Case 2: Facet-Level Analysis

**Goal:** See how different finishes perform, ignoring brands

**Action:**
1. Check "Hide Entities column"

**Result:** Facet-level metrics!

```
Category Mapping | Features  | Monthly Traffic
Paint            | Washable  | 8,000
Paint            | Quick Dry | 5,000
Paint            | Matte     | 2,000
```

---

### Use Case 3: Brand Comparison

**Goal:** Keep brands visible to compare performance

**Action:**
1. Check "Hide Features column"

**Result:** Brand-level metrics!

```
Category Mapping | Entities       | Monthly Traffic
Paint            | Dulux          | 7,000
Paint            | Crown          | 5,000
Paint            | Johnstone's    | 3,000
```

---

## Technical Implementation

### How It Works Under the Hood

1. **User checks "Hide Entities column"**
   ```javascript
   tableState.hideEntities = true
   ```

2. **Build exclusion list**
   ```javascript
   excludeFromAggregation = ['Entities', 'Discovered Entities']
   ```

3. **Pass to aggregation function**
   ```javascript
   applyOverridesAndMerge(data, headers, hasOnsite, excludeFromAggregation)
   ```

4. **Filter facet headers**
   ```javascript
   facetHeaders = headers.filter(h => 
       h !== 'Category Mapping' && 
       !h.includes('Traffic') && 
       !excludeFromAggregation.includes(h)
   )
   ```

5. **Build aggregation key WITHOUT excluded columns**
   ```javascript
   const key = [
       modifiedFacets['Category Mapping'] || '', 
       ...facetHeaders.map(h => modifiedFacets[h] || '')
   ].join('||')
   ```

6. **Rows with same key merge**
   - Metrics are summed
   - Keywords are combined
   - Result: Fewer, more meaningful rows!

---

## Benefits

### ✅ Cleaner Data
- No duplicate-looking rows
- True aggregated metrics
- Easier to analyze

### ✅ More Accurate Insights
- See category-level performance
- Understand facet impact
- Compare at the right granularity

### ✅ Better Exports
- Excel/CSV exports show merged data
- Fewer rows, more meaningful
- Perfect for presentations

### ✅ Flexible Analysis
- Toggle columns on/off to change granularity
- Drill down or roll up as needed
- Same data, multiple views

---

## Comparison Table

| Feature | Without Re-Aggregation | With Re-Aggregation ✨ |
|---------|----------------------|----------------------|
| Hide column | Column disappears | Column disappears + rows merge |
| Row count | Stays the same | Decreases (merged rows) |
| Metrics | Spread across rows | Summed in merged rows |
| Keywords | Spread across rows | Combined in merged rows |
| Analysis | Confusing duplicates | Clean aggregated data |
| Exports | Many similar rows | Fewer meaningful rows |

---

## Important Notes

### ✅ Non-Destructive
- Original data is preserved
- Uncheck boxes to see original rows
- Completely reversible

### ✅ Real-Time
- Merging happens instantly
- No lag or loading time
- Immediate visual feedback

### ✅ Works with Manual Overrides
- Re-aggregation happens AFTER override rules
- Rules are applied first
- Then hidden columns trigger merging

### ⚠️ Session-Based
- Checkbox state resets on page reload
- Not persisted between sessions
- Re-check boxes as needed

---

## FAQ

**Q: Will hiding columns change my total metrics?**  
A: No! Total traffic, searches, etc. stay the same. They're just distributed across fewer rows.

**Q: Can I see the original separate rows?**  
A: Yes! Just uncheck the "Hide" boxes and the rows split back out.

**Q: What if I hide all facet columns?**  
A: You'll get one row per category with all metrics summed.

**Q: Do exports include the merged data?**  
A: Yes! Excel/CSV/PDF exports show the merged, aggregated data.

**Q: Can I hide other columns dynamically?**  
A: Currently only Entities and Features have this feature, but more can be added.

**Q: Does this work with "Delete & Remove" rules?**  
A: Yes! Removed rows are excluded first, then remaining rows merge.

**Q: Will keyword details get too long?**  
A: They're stored in an expandable list. Click ▶ to view all keywords.

---

## Examples in Action

### Example 1: Simple Category Analysis

**Start with this:**
```
Paint | Dulux     | Washable  | 2,000
Paint | Crown     | Washable  | 3,000
Paint | Dulux     | Quick Dry | 1,500
Stain | Ronseal   | Interior  | 4,000
```

**Check both "Hide Entities" and "Hide Features":**
```
Paint → 6,500 (3 rows merged!)
Stain → 4,000 (1 row)
```

**Total rows:** 4 → 2  
**Insight:** Paint generates 6,500 traffic, Stain generates 4,000

---

### Example 2: Facet Impact Analysis

**Start with this:**
```
Paint | Dulux     | Washable  | 2,000
Paint | Crown     | Washable  | 3,000
Paint | Dulux     | Quick Dry | 1,500
Paint | Crown     | Quick Dry | 2,500
```

**Check "Hide Entities" only:**
```
Paint | Washable  → 5,000 (2 rows merged)
Paint | Quick Dry → 4,000 (2 rows merged)
```

**Insight:** Washable feature generates more traffic than Quick Dry!

---

## Version Information

**Feature:** Dynamic Re-Aggregation  
**Version:** 1.5  
**Date:** 2025-11-06  
**Status:** ✅ Complete and Production Ready  
**Works with:** Hide Entities/Features columns

---

## Summary

✅ **Automatic merging** when columns are hidden  
✅ **Metrics are summed** for cleaner insights  
✅ **Keywords are combined** in expandable lists  
✅ **Real-time updates** with instant feedback  
✅ **Non-destructive** and completely reversible  

**Your data now aggregates dynamically for better analysis!** 🎉

