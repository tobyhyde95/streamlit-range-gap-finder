#!/usr/bin/env python3
"""
Diagnostic tool to help identify why SKU matching is failing.
This tool analyzes the actual data being processed.
"""

import sys
import json
from seo_analyzer.pim_sku_analyzer import (
    analyze_pim_skus,
    _normalize_value,
    _category_required_tokens,
    _category_tokens_present
)

def diagnose_category_facet_map(category_facet_map):
    """Analyze the category-facet map to see what categories are present."""
    print("=" * 80)
    print("CATEGORY-FACET MAP ANALYSIS")
    print("=" * 80)
    
    categories = {}
    for pair in category_facet_map:
        cat = pair.get('Category Mapping', '').strip()
        if cat:
            if cat not in categories:
                categories[cat] = []
            categories[cat].append({
                'facet_attribute': pair.get('Facet Attribute', ''),
                'facet_value': pair.get('Facet Value', '')
            })
    
    print(f"\nTotal unique categories: {len(categories)}")
    
    # Check for specific categories
    search_terms = ['climb', 'masonry', 'mould', 'damp']
    print("\nCategories containing search terms:")
    for term in search_terms:
        matching = [cat for cat in categories.keys() if term.lower() in cat.lower()]
        if matching:
            print(f"  '{term}': {len(matching)} categories")
            for cat in matching[:5]:
                print(f"    - {cat}")
        else:
            print(f"  '{term}': 0 categories found")
    
    # Show sample categories
    print(f"\nSample categories (first 20):")
    for i, cat in enumerate(list(categories.keys())[:20], 1):
        print(f"  {i}. {cat}")


def diagnose_sku_data(pim_csv_path):
    """Analyze the SKU data to see what's being processed."""
    import pandas as pd
    
    print("\n" + "=" * 80)
    print("SKU DATA ANALYSIS")
    print("=" * 80)
    
    try:
        df = pd.read_csv(pim_csv_path)
        print(f"\nTotal SKUs: {len(df)}")
        print(f"Columns: {list(df.columns)}")
        
        # Check for SKU ID column
        sku_id_col = None
        for col in df.columns:
            if 'sku' in col.lower() or 'product code' in col.lower() or 'id' in col.lower():
                sku_id_col = col
                break
        
        if sku_id_col:
            print(f"\nSKU ID column: {sku_id_col}")
            print(f"SKU IDs: {df[sku_id_col].tolist()}")
        else:
            print("\n⚠️  Could not identify SKU ID column")
        
        # Check for product name column
        name_cols = [col for col in df.columns if 'name' in col.lower() or 'part' in col.lower()]
        if name_cols:
            print(f"\nProduct name columns: {name_cols}")
            for col in name_cols[:2]:
                print(f"\nSample values from '{col}':")
                for idx, val in df[col].head(5).items():
                    if pd.notna(val):
                        print(f"  SKU {df[sku_id_col].iloc[idx] if sku_id_col else idx}: {str(val)[:80]}")
        
        # Check for specific terms in all text columns
        search_terms = ['climb', 'masonry', 'mould', 'anti']
        print(f"\nSearching for terms in all text columns:")
        for term in search_terms:
            found = []
            for idx, row in df.iterrows():
                row_text = ' '.join([str(v) for v in row.values if pd.notna(v)]).lower()
                if term.lower() in row_text:
                    sku_id = row[sku_id_col] if sku_id_col else idx
                    found.append(sku_id)
            if found:
                print(f"  '{term}': Found in {len(found)} SKUs - {found}")
            else:
                print(f"  '{term}': Not found in any SKU")
        
    except Exception as e:
        print(f"ERROR reading SKU data: {e}")
        import traceback
        traceback.print_exc()


def test_specific_match(category, sku_data, category_facet_map):
    """Test matching for a specific category and SKU."""
    print("\n" + "=" * 80)
    print(f"TESTING MATCH: '{category}'")
    print("=" * 80)
    
    # Find the category in the map
    category_pairs = [p for p in category_facet_map if p.get('Category Mapping', '').strip() == category]
    if not category_pairs:
        print(f"❌ Category '{category}' not found in category-facet map!")
        return
    
    print(f"✓ Found {len(category_pairs)} pair(s) for category '{category}'")
    
    # Extract required tokens
    required_tokens = _category_required_tokens(category)
    print(f"Required tokens: {required_tokens}")
    
    # Test against each SKU
    import pandas as pd
    for sku_id, sku_row in sku_data.items():
        print(f"\n--- Testing SKU {sku_id} ---")
        
        # Get all text from SKU
        sku_text = ' '.join([str(v) for v in sku_row.values() if v and str(v).strip()])
        sku_normalized = _normalize_value(sku_text)
        
        print(f"SKU text (first 200 chars): {sku_text[:200]}")
        print(f"SKU normalized (first 200 chars): {sku_normalized[:200]}")
        
        # Check tokens
        tokens_present = _category_tokens_present(required_tokens, sku_normalized)
        print(f"Tokens present: {tokens_present}")
        
        if tokens_present:
            print(f"✓ SKU {sku_id} SHOULD match '{category}'")
        else:
            print(f"✗ SKU {sku_id} will NOT match '{category}'")
            
            # Show why
            for token in required_tokens:
                token_words = token.split()
                if len(token_words) > 1:
                    phrase_present = token in sku_normalized
                    words_present = all(word in sku_normalized for word in token_words)
                    print(f"  Token '{token}': phrase={phrase_present}, words={words_present}")
                else:
                    word_present = token in sku_normalized
                    print(f"  Token '{token}': present={word_present}")


def main():
    """Main diagnostic function."""
    if len(sys.argv) < 2:
        print("Usage: python diagnose_pim_issue.py <pim_csv_path> [category_facet_map_json]")
        print("\nExample:")
        print("  python diagnose_pim_issue.py pim_data.csv")
        print("  python diagnose_pim_issue.py pim_data.csv category_map.json")
        sys.exit(1)
    
    pim_csv_path = sys.argv[1]
    
    # Load category-facet map if provided
    category_facet_map = []
    if len(sys.argv) >= 3:
        with open(sys.argv[2], 'r') as f:
            category_facet_map = json.load(f)
    else:
        # Create a test map with common categories
        category_facet_map = [
            {'Category Mapping': 'Anti Climb Paint', 'Facet Attribute': 'Root Category', 'Facet Value': 'Root Category'},
            {'Category Mapping': 'Masonry Paint', 'Facet Attribute': 'Root Category', 'Facet Value': 'Root Category'},
            {'Category Mapping': 'Anti Mould Paint', 'Facet Attribute': 'Root Category', 'Facet Value': 'Root Category'},
        ]
        print("⚠️  No category-facet map provided, using test map")
    
    # Run diagnostics
    diagnose_category_facet_map(category_facet_map)
    diagnose_sku_data(pim_csv_path)
    
    # Test specific matches
    import pandas as pd
    df = pd.read_csv(pim_csv_path)
    sku_id_col = None
    for col in df.columns:
        if 'sku' in col.lower() or 'product code' in col.lower():
            sku_id_col = col
            break
    
    if sku_id_col:
        sku_data = {}
        for idx, row in df.iterrows():
            sku_id = str(row[sku_id_col])
            sku_data[sku_id] = row.to_dict()
        
        test_specific_match('Anti Climb Paint', sku_data, category_facet_map)
        test_specific_match('Masonry Paint', sku_data, category_facet_map)
    
    print("\n" + "=" * 80)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 80)
    print("\nNext steps:")
    print("1. Check if categories exist in your Category Overhaul Matrix")
    print("2. Verify the category names match exactly (case, spaces, hyphens)")
    print("3. Check if SKU data contains the expected text")
    print("4. Export your category-facet map as JSON and run:")
    print(f"   python diagnose_pim_issue.py {pim_csv_path} category_map.json")


if __name__ == "__main__":
    main()

