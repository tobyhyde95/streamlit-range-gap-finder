# New Features Summary

## ✅ Two New Features Implemented

Both requested features have been fully implemented and are ready to use!

---

## Feature 1: Delete and Remove Action

### What It Does

Adds a new **"Delete & Remove"** action that completely removes rows from the dataset (unlike "Delete & Merge" which keeps rows with blank values).

### The Difference

| Action | Behavior | Use Case |
|--------|----------|----------|
| **Delete & Merge** | Removes value but keeps row with blank | Clean up data while preserving row structure |
| **Delete & Remove** ✨ NEW | Completely removes rows from dataset | Remove unrelated data entirely |

### Example

**Scenario:** You have some rows with Category Mapping = "Unrelated Product" that don't belong in your analysis.

**Before:**
| Category Mapping | Monthly Traffic | Keywords |
|------------------|----------------|----------|
| Paint | 5,000 | 150 |
| Unrelated Product | 500 | 20 |
| Wood Stain | 3,000 | 80 |

**Using "Delete & Merge"** on "Unrelated Product":
| Category Mapping | Monthly Traffic | Keywords |
|------------------|----------------|----------|
| Paint | 5,000 | 150 |
| *(blank)* | 500 | 20 |
| Wood Stain | 3,000 | 80 |

**Using "Delete & Remove"** ✨ on "Unrelated Product":
| Category Mapping | Monthly Traffic | Keywords |
|------------------|----------------|----------|
| Paint | 5,000 | 150 |
| Wood Stain | 3,000 | 80 |

✅ Row completely removed from table, exports, and all calculations!

### How to Use

1. Go to **Manual Overrides** → **Value-Based Rules**
2. Select your column (e.g., Category Mapping)
3. Select the value(s) you want to remove
4. Set Action to **"Delete & Remove"** ✨
5. Click **+ Add Rule(s)**
6. Rows with that value are immediately removed from the view!

### Visual Indicator

Rules show a red badge:

```
From Category Mapping, delete & remove rows with value "Unrelated Product" (removes rows)
```

---

## Feature 2: Hide Entities and Features Columns

### What It Does

Adds **checkbox controls** to hide the Entities and Features columns from the Category Overhaul Matrix view.

### Why You Need It

- Entities and Features columns can clutter the view
- Not always relevant to your analysis
- Makes the table cleaner and easier to navigate
- Hides columns without deleting data

### Where to Find It

In the **Category Overhaul Matrix** view, you'll see these new checkboxes:

```
☐ Hide rows with 0 traffic
☐ Hide Entities column     ← NEW!
☐ Hide Features column     ← NEW!
```

### How It Works

**Check the box** → Column immediately disappears from view
**Uncheck the box** → Column reappears

✅ State is preserved as you navigate
✅ Applies to table view and exports
✅ Data is not deleted, just hidden

### Example

**Before (all columns visible):**
| Category Mapping | Entities | Features | Monthly Traffic |
|------------------|----------|----------|----------------|
| Paint | Dulux, Crown | Washable, Quick Dry | 5,000 |
| Wood Stain | Ronseal | Interior | 3,000 |

**After checking "Hide Entities column" and "Hide Features column":**
| Category Mapping | Monthly Traffic |
|------------------|----------------|
| Paint | 5,000 |
| Wood Stain | 3,000 |

Much cleaner! ✨

### Columns Hidden

When you check the boxes, these columns are hidden:

- **Hide Entities**: Hides `Entities` and `Discovered Entities`
- **Hide Features**: Hides `Features` and `Discovered Features`

---

## Technical Details

### Files Modified

**`assets/js/app.js`**
- Line 6-12: Added `hideEntities` and `hideFeatures` to tableState
- Line 51-106: Implemented "Delete & Remove" logic in `applyOverridesAndMerge`
- Line 899-914: Added "Delete & Remove" display in active rules
- Line 945-952: Added "Delete & Remove" to action dropdown
- Line 2148-2189: Implemented column visibility checkboxes

### No Linting Errors ✅

Both features have been tested and pass all linting checks.

---

## Quick Start Guide

### Delete & Remove

```
1. Manual Overrides → Value-Based Rules
2. Select column with unwanted data
3. Select value(s) to remove
4. Action → "Delete & Remove"
5. Add Rule → Rows disappear!
```

### Hide Columns

```
1. View Category Overhaul Matrix
2. Check "Hide Entities column" and/or "Hide Features column"
3. Columns disappear immediately
4. Uncheck to show again
```

---

## Use Cases

### Delete & Remove - Best For:

✅ Removing test data or outliers  
✅ Filtering out unrelated products  
✅ Cleaning up imported data with junk rows  
✅ Focusing analysis on specific categories  

### Hide Columns - Best For:

✅ Simplifying complex tables  
✅ Focusing on core taxonomy data  
✅ Creating cleaner exports for presentations  
✅ Reducing cognitive load when analyzing data

---

## Important Notes

### Delete & Remove

⚠️ **Destructive Action**: Rows are removed from the current view and exports
✅ **Reversible**: Remove the rule to bring rows back
✅ **Session-based**: Original data is preserved (rules don't persist between reloads)

### Hide Columns

✅ **Non-destructive**: Data is not deleted, just hidden
✅ **Persistent**: State is maintained during your session
✅ **Export-friendly**: Hidden columns are excluded from exports

---

## Examples in Context

### Example 1: Cleaning Up Category Data

**Problem:** Some rows have "Misc" or "Other" in Category Mapping that aren't useful.

**Solution:**
1. Select Category Mapping column
2. Select "Misc" and "Other" values
3. Action: "Delete & Remove"
4. Add Rule

**Result:** Clean dataset focused on real categories!

---

### Example 2: Focusing on Core Taxonomy

**Problem:** Entities and Features columns are distracting from the main category analysis.

**Solution:**
1. Check "Hide Entities column"
2. Check "Hide Features column"

**Result:** Clean view showing just Category Mapping, facets, and metrics!

---

## FAQ

**Q: Can I undo "Delete & Remove"?**  
A: Yes! Click the × button next to the rule to remove it. The rows will reappear.

**Q: Will hidden columns appear in exports?**  
A: No, hidden columns are excluded from Excel, CSV, and PDF exports.

**Q: Can I use multiple "Delete & Remove" rules?**  
A: Yes! Add multiple rules to remove different values or from different columns.

**Q: Do the checkboxes persist between page reloads?**  
A: No, they reset when you reload the page (session-based).

**Q: Can I hide other columns?**  
A: Currently only Entities and Features have dedicated checkboxes. More can be added if needed.

---

## Version Information

**Feature Version:** 1.4  
**Implementation Date:** 2025-11-06  
**Status:** ✅ Complete and Production Ready  
**Backward Compatibility:** ✅ All existing functionality preserved

---

## Summary

✅ **Delete & Remove** - Completely remove unwanted rows from your analysis  
✅ **Hide Entities/Features** - Simplify your table view with checkbox controls

Both features work together to give you more control over your data presentation and analysis!

Enjoy your cleaner, more focused analysis! 🎉

