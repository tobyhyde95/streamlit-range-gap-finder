# Delete & Remove Feature Documentation

## Overview

The **Delete & Remove** action allows you to completely remove rows from your dataset based on matching values in any column. Unlike **Delete & Merge** which keeps rows with blank values, **Delete & Remove** eliminates rows entirely.

---

## The Key Difference

### Delete & Merge (Existing)
```
Removes the value → Leaves row with blank value → Row stays in dataset
```

**Example:**
```
Before: Category Mapping = "Unwanted"
After:  Category Mapping = (blank)
        Row still appears in table with 0 values in that column
```

---

### Delete & Remove (NEW) ✨
```
Finds matching value → Removes entire row → Row gone from dataset
```

**Example:**
```
Before: Category Mapping = "Unwanted"
After:  Row completely removed from table, counts, exports, everything
```

---

## When to Use Each Action

### Use "Delete & Merge" When:

✅ You want to clean up a specific column but preserve the row  
✅ The data might be useful later with a blank value  
✅ You're consolidating categories and want to keep traffic metrics  
✅ You want rows to merge with other blank-value rows

### Use "Delete & Remove" When:

✅ Rows are completely unrelated to your analysis  
✅ Data is test/junk data that should be excluded  
✅ You want to focus only on specific categories  
✅ Rows would distort your overall metrics if kept

---

## How It Works

### Step-by-Step Guide

1. **Navigate to Manual Overrides**
   - Find the "Manual Overrides" section
   - Select the "Value-Based Rules" tab

2. **Select Your Column**
   - Choose the column containing the values you want to remove
   - Common choice: "Category Mapping"

3. **Select Value(s) to Remove**
   - The value listbox shows all unique values in that column
   - You can select multiple values at once
   - Use the filter box to search for specific values

4. **Choose "Delete & Remove" Action**
   - Set Action dropdown to **"Delete & Remove"**
   - This is the new option alongside "Delete & Merge"

5. **Add the Rule**
   - Click **+ Add Rule(s)**
   - Rules are immediately applied
   - Table refreshes to show remaining data

6. **Verify Results**
   - Check that unwanted rows are gone
   - Verify metrics reflect only remaining data
   - Export to confirm changes

---

## Visual Examples

### Example 1: Removing Unrelated Products

**Scenario:** Your dataset includes "Garden Furniture" but you're analyzing only paint products.

**Dataset Before:**
| Category Mapping | Monthly Traffic | Keyword Count |
|------------------|----------------|---------------|
| Exterior Paint | 5,000 | 150 |
| Interior Paint | 8,000 | 200 |
| Garden Furniture | 2,000 | 50 |
| Wood Stain | 3,000 | 80 |
| Garden Decking | 1,500 | 40 |

**Rule Applied:**
```
From Category Mapping, delete & remove rows with value "Garden Furniture" (removes rows)
From Category Mapping, delete & remove rows with value "Garden Decking" (removes rows)
```

**Dataset After:**
| Category Mapping | Monthly Traffic | Keyword Count |
|------------------|----------------|---------------|
| Exterior Paint | 5,000 | 150 |
| Interior Paint | 8,000 | 200 |
| Wood Stain | 3,000 | 80 |

✅ **Total Traffic:** Reduced from 19,500 to 16,000 (accurate)  
✅ **Total Keywords:** Reduced from 520 to 430 (accurate)  
✅ **Focus:** Only relevant paint/stain products remain

---

### Example 2: Filtering by Facet Value

**Scenario:** You only want to analyze products with "Professional" quality, removing "DIY" products.

**Dataset Before:**
| Category Mapping | Quality | Monthly Traffic |
|------------------|---------|----------------|
| Paint | Professional | 5,000 |
| Paint | DIY | 3,000 |
| Primer | Professional | 2,000 |
| Primer | DIY | 1,500 |

**Rule Applied:**
```
From Quality, delete & remove rows with value "DIY" (removes rows)
```

**Dataset After:**
| Category Mapping | Quality | Monthly Traffic |
|------------------|---------|----------------|
| Paint | Professional | 5,000 |
| Primer | Professional | 2,000 |

✅ Analysis now focused entirely on Professional products!

---

## Technical Implementation

### How Rows Are Filtered

```javascript
// When a "remove" action rule matches:
if (rule.action === 'remove') {
    if (ruleValue !== '' && !isCellBlank && cellValues.includes(ruleValue)) {
        shouldRemoveRow = true;
    }
}

// Later in the processing:
if (shouldRemoveRow) {
    return; // Skip adding this row to the output
}
```

### What Gets Removed

When a row is marked for removal:

- ❌ Row disappears from the table view
- ❌ Excluded from all metric calculations
- ❌ Removed from exports (Excel, CSV, PDF, JSON)
- ❌ Keywords associated with that row are not counted
- ❌ Traffic/search volume not included in totals

### What Gets Preserved

- ✅ Original data remains intact (in memory)
- ✅ Removing the rule brings rows back
- ✅ Other rows are unaffected
- ✅ No data is permanently deleted

---

## Multiple Value Selection

You can select multiple values at once to remove all matching rows:

### Example:

**Select Multiple Values:**
```
☑ Test Product
☑ Sample Data
☑ Demo Category
☑ Placeholder
```

**One Rule Created Per Value:**
```
From Category Mapping, delete & remove rows with value "Test Product" (removes rows)
From Category Mapping, delete & remove rows with value "Sample Data" (removes rows)
From Category Mapping, delete & remove rows with value "Demo Category" (removes rows)
From Category Mapping, delete & remove rows with value "Placeholder" (removes rows)
```

**Result:** All rows with any of these values are removed!

---

## Rule Management

### Viewing Active Rules

Active rules are displayed with a red badge to indicate they remove rows:

```
From Category Mapping, delete & remove rows with value "Unwanted" (removes rows)
```

### Removing Rules

Click the **×** button next to any rule to remove it:

```
From Category Mapping, delete & remove rows... [×]
```

When you remove a rule:
- Rows immediately reappear
- Metrics are recalculated
- Table refreshes automatically

### Clearing All Rules

Click **Clear All Rules** to remove all active rules at once.

---

## Impact on Other Features

### Exports

**Excel/CSV Exports:**
- Removed rows do NOT appear
- Totals reflect only remaining rows
- Keyword Details exclude removed rows

**PDF Exports:**
- Only remaining rows are included
- Page counts based on filtered data

**JSON Exports:**
- Removed rows are excluded from the data payload
- Metadata reflects filtered counts

### Facet Potential Analysis

- Removed rows are excluded from facet calculations
- Facet value scores recalculated without removed data
- More accurate insights into remaining categories

### Manual Overrides

- Other rules can still apply to remaining data
- "Delete & Remove" rules process first
- Change/Move rules only affect rows that weren't removed

---

## Best Practices

### 1. Start Broad, Then Refine

```
Step 1: Remove obviously unrelated categories
Step 2: Review remaining data
Step 3: Remove edge cases or outliers
Step 4: Fine-tune with Change/Move rules
```

### 2. Use Descriptive Selections

Select entire values rather than partial matches:
- ✅ "Garden Furniture" (specific)
- ❌ "Garden" (might match "Garden Paint" too)

### 3. Preview Before Removing

1. Add one rule at a time initially
2. Review the results
3. Verify metrics make sense
4. Then add bulk removals if confident

### 4. Document Your Choices

Keep track of what you removed and why:
```
Removed: Garden Furniture, Garden Decking
Reason: Out of scope for paint analysis
Date: 2025-11-06
```

---

## Common Scenarios

### Scenario 1: Testing and Development Data

**Problem:** Dataset includes "Test", "Sample", "Demo" products

**Solution:**
```
Select: Test Product, Sample, Demo, Placeholder
Action: Delete & Remove
Result: Clean production data only
```

---

### Scenario 2: Geographic Filtering

**Problem:** Want to analyze only UK data, remove other regions

**Solution:**
```
Column: Region
Select: USA, EU, Asia, Other
Action: Delete & Remove
Result: Only UK rows remain
```

---

### Scenario 3: Quality Filtering

**Problem:** Focus on premium products only

**Solution:**
```
Column: Product Tier
Select: Basic, Standard
Action: Delete & Remove
Result: Only Premium tier remains
```

---

### Scenario 4: Time-based Filtering

**Problem:** Remove old/discontinued products

**Solution:**
```
Column: Status
Select: Discontinued, Deprecated, Legacy
Action: Delete & Remove
Result: Only current products in analysis
```

---

## Troubleshooting

### "Rule added but rows still showing"

**Check:**
- Is the exact value selected?
- Values are case-sensitive
- Spaces matter (trim if needed)

**Solution:** Use the value filter to find exact match

---

### "Removed too many rows by accident"

**Solution:**
- Click × button next to the rule
- Rows will immediately reappear
- Review and create a more specific rule

---

### "Want to remove by multiple criteria"

**Solution:**
- Create multiple rules
- Each rule targets a different column/value
- All conditions are applied together

---

## Keyboard Shortcuts

None specific to this feature, but general shortcuts apply:
- **Tab**: Navigate between fields
- **Space**: Select values in listbox
- **Enter**: Submit form (add rules)

---

## Limitations

- ⚠️ Rules are session-based (not saved between page reloads)
- ⚠️ Cannot use wildcards (exact value matches only)
- ⚠️ Cannot remove based on numeric ranges (select specific values)
- ⚠️ Blank values cannot be used with "Delete & Remove"

---

## FAQ

**Q: What's the difference from Delete & Merge again?**  
A: Delete & Merge keeps the row with a blank value. Delete & Remove completely eliminates the row.

**Q: Can I remove rows based on traffic levels?**  
A: Not directly. You'd need to identify and select the specific category/facet values that have low traffic.

**Q: Are rows permanently deleted?**  
A: No! Removing the rule brings them back. Original data is preserved.

**Q: Can I export the list of removed rows?**  
A: Not directly, but you can note which values were removed in your rules list.

**Q: What if I remove all rows by mistake?**  
A: Click "Clear All Rules" and all rows will return.

**Q: Can I remove blank values?**  
A: No, "Delete & Remove" only works with non-blank values. Use filters instead for blank rows.

---

## Version Information

**Feature:** Delete & Remove  
**Version:** 1.4  
**Date:** 2025-11-06  
**Status:** ✅ Production Ready  
**Dependencies:** None

---

## Summary

**Delete & Remove** is your tool for completely filtering out unwanted rows from your analysis. Use it to:

✅ Remove unrelated products/categories  
✅ Filter out test/sample data  
✅ Focus analysis on specific segments  
✅ Clean up datasets quickly  

Remember: It's reversible, session-based, and non-destructive to your original data!

---

**Ready to clean up your data? Start removing those unwanted rows!** 🎯

