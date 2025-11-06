# Move Mode Feature: Append vs Replace

## Overview

When using the "Move Value" action in Manual Overrides, you now have two options for how values are moved to the target column:

1. **Move and Append** (default) - Keeps existing value and adds the new value with a pipe separator
2. **Move and Replace** - Completely replaces the existing value with the new value

---

## How It Works

### Move and Append (Default Behavior)

**Example:**
- **Source Column:** `Navigation_Type` with value `"Anti Mould"`
- **Target Column:** `Category Mapping` with existing value `"Paint"`
- **Action:** Move "Anti Mould" from Navigation_Type to Category Mapping (Append mode)
- **Result:** Category Mapping becomes `"Anti Mould | Paint"`

The value is appended to existing values with a pipe (`|`) separator and sorted alphabetically.

---

### Move and Replace (New Option)

**Example:**
- **Source Column:** `Navigation_Type` with value `"Anti Mould"`  
- **Target Column:** `Category Mapping` with existing value `"Paint"`
- **Action:** Move "Anti Mould" from Navigation_Type to Category Mapping (Replace mode)
- **Result:** Category Mapping becomes `"Anti Mould"` (Paint is replaced)

The existing value is completely overwritten with the moved value.

---

## Using the Feature

### Step 1: Set Up Your Rule

1. Navigate to the **Manual Overrides** section
2. Select the **Value-Based Rules** tab
3. Choose your **Column** (e.g., Navigation_Type)
4. Select the **Value(s)** you want to move
5. Set **Action** to "Move Value"

### Step 2: Choose Your Move Mode

When you select "Move Value" as the action, you'll see two new options:

```
Move Mode:
○ Append (keep existing & add)     ← Default
○ Replace (overwrite existing)
```

- **Append**: Select this to keep the existing value and add the new value with a pipe separator
- **Replace**: Select this to completely overwrite the existing value

### Step 3: Select Target Column

Choose where you want to move the value to:
- Select an existing column from the dropdown, OR
- Check "Create new column" and enter a new column name

### Step 4: Add the Rule

Click **+ Add Rule(s)** to apply your configuration.

---

## Visual Indicators

Active rules now show the move mode with color-coded badges:

- **Append mode**: <span style="background-color: #dbeafe; color: #1e40af; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem;">(append)</span>
- **Replace mode**: <span style="background-color: #fed7aa; color: #9a3412; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem;">(replace)</span>

**Example display:**
```
From Navigation_Type, move value "Anti Mould" to Category Mapping (append)
From Sub Type, move value "Gloss" to Category Mapping (replace)
```

---

## Immediate Updates

After adding a rule, the **table automatically refreshes** to show the updated values. You can:

1. ✅ See the updated value immediately in the target column
2. ✅ Create additional mapping rules based on the new value
3. ✅ Edit or refine the moved value with further rules
4. ✅ Export the data with the applied changes

---

## Common Use Cases

### Use Case 1: Building a Category (Append)

**Scenario:** You want to build a comprehensive Category Mapping by combining values from multiple columns.

**Example:**
```
Step 1: Move "Exterior" from Location → Category Mapping (Append)
  Result: Category Mapping = "Exterior"

Step 2: Move "Wood" from Material → Category Mapping (Append)
  Result: Category Mapping = "Exterior | Wood"

Step 3: Move "Paint" from Product_Type → Category Mapping (Append)
  Result: Category Mapping = "Exterior | Paint | Wood"
```

---

### Use Case 2: Correcting Categorization (Replace)

**Scenario:** The Category Mapping has an incorrect value that needs to be completely replaced.

**Example:**
```
Current State:
  Category Mapping = "Paint" (too generic)
  Navigation_Type = "Anti Mould Paint"

Action: Move "Anti Mould Paint" from Navigation_Type → Category Mapping (Replace)

Result:
  Category Mapping = "Anti Mould Paint" (correct and specific)
  Navigation_Type = (empty/removed)
```

---

### Use Case 3: Consolidating Facets (Append)

**Scenario:** Multiple columns contain related facet information that should be combined.

**Example:**
```
Current State:
  Finish = "Matte"
  Surface_Type = "Textured"

Action: Move "Textured" from Surface_Type → Finish (Append)

Result:
  Finish = "Matte | Textured"
  Surface_Type = (empty/removed)
```

---

## Tips & Best Practices

### When to Use Append

✅ **Building composite categories** from multiple data sources  
✅ **Preserving existing data** while adding new information  
✅ **Combining related facet values** that should coexist  
✅ **Merging complementary attributes** (e.g., "Indoor" + "Outdoor")

### When to Use Replace

✅ **Correcting incorrect categorization** completely  
✅ **Simplifying overcomplicated values** to a single term  
✅ **Normalizing categories** to a standard format  
✅ **Overwriting generic values** with specific ones

---

## Technical Details

### Data Flow

1. **Rule Application**: Rules are applied in the order they were created
2. **Value Removal**: The value is removed from the source column
3. **Target Update**: Based on move mode:
   - **Append**: Value added to existing values, pipe-separated, sorted
   - **Replace**: Existing value completely overwritten
4. **Table Refresh**: The view automatically re-renders with updated data
5. **Export Ready**: Changes are reflected in all exports (Excel, CSV, PDF)

### Persistence

- ✅ Rules remain active until manually removed
- ✅ Rules apply to all matching rows in the dataset
- ✅ Changes are reflected in real-time across all views
- ⚠️ Rules are session-based (not persisted between page reloads)

---

## Keyboard Workflow

For power users, here's a keyboard-optimized workflow:

1. **Tab** to Column dropdown → Select source
2. **Tab** to Values listbox → **Arrow keys** to navigate, **Space** to select
3. **Tab** to Action dropdown → Select "Move Value"
4. **Tab** through radio buttons → **Space** to toggle Append/Replace
5. **Tab** to Target dropdown → Select destination
6. **Tab** to Add Rule button → **Enter** to apply

---

## FAQ

**Q: Can I move multiple values at once?**  
A: Yes! Select multiple values from the listbox before adding the rule. Each value will have the same move mode applied.

**Q: What happens if the target column is empty?**  
A: Both modes work the same - the value is simply placed in the empty column.

**Q: Can I undo a move?**  
A: Yes, use the **×** button next to the rule in the Active Rules list to remove it. The table will refresh showing the original data.

**Q: How do I see the updated values?**  
A: The table automatically refreshes when you add a rule. The updated values are immediately visible in the target column.

**Q: Can I create additional rules based on moved values?**  
A: Absolutely! Once a value is moved, you can create new rules that target the updated column with the new value.

**Q: Do the changes persist in exports?**  
A: Yes, all Excel, CSV, and PDF exports include the transformed data with all rules applied.

---

## Release Information

**Feature Version:** 1.3  
**Date:** 2025-11-06  
**Status:** ✅ Production Ready  
**Backward Compatibility:** ✅ Existing rules default to "Append" mode

---

## Example Scenarios

### Scenario 1: Fixing Incorrect Category

**Before:**
| Keyword | Category Mapping | Navigation_Type |
|---------|------------------|-----------------|
| anti mould paint | Paint | Anti Mould |

**Rule:** Move "Anti Mould" from Navigation_Type to Category Mapping (Replace)

**After:**
| Keyword | Category Mapping | Navigation_Type |
|---------|------------------|-----------------|
| anti mould paint | Anti Mould | |

---

### Scenario 2: Building Rich Categories

**Before:**
| Keyword | Category Mapping | Material | Location |
|---------|------------------|----------|----------|
| exterior wood paint | Paint | Wood | Exterior |

**Rules:**
1. Move "Wood" from Material to Category Mapping (Append)
2. Move "Exterior" from Location to Category Mapping (Append)

**After:**
| Keyword | Category Mapping | Material | Location |
|---------|------------------|----------|----------|
| exterior wood paint | Exterior \| Paint \| Wood | | |

---

## Support

For questions or issues with this feature, please refer to the inline help in the application or consult the main documentation.

