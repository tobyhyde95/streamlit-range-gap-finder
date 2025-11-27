#!/usr/bin/env python3
"""
Comprehensive test script for SKU matching logic.
This script helps diagnose why categories aren't matching SKUs.
"""

import pandas as pd
import json
from seo_analyzer.pim_sku_analyzer import (
    analyze_pim_skus,
    _normalize_value,
    _category_required_tokens,
    _category_tokens_present,
    _intelligent_match
)

def test_normalization():
    """Test that normalization works correctly."""
    print("=" * 80)
    print("TEST 1: Normalization")
    print("=" * 80)
    
    test_cases = [
        ("Anti Climb Paint", "Anti-Climb Paint"),
        ("Anti Climb Paint", "Anti_Climb Paint"),
        ("Masonry Paint", "Masonry Paint"),
        ("Masonry Paint", "Masonry-Paint"),
    ]
    
    for category, sku_text in test_cases:
        cat_norm = _normalize_value(category)
        sku_norm = _normalize_value(sku_text)
        print(f"\nCategory: '{category}' -> '{cat_norm}'")
        print(f"SKU: '{sku_text}' -> '{sku_norm}'")
        print(f"Match: {cat_norm == sku_norm or cat_norm in sku_norm or sku_norm in cat_norm}")


def test_token_extraction():
    """Test that required tokens are extracted correctly."""
    print("\n" + "=" * 80)
    print("TEST 2: Token Extraction")
    print("=" * 80)
    
    categories = [
        "Anti Climb Paint",
        "Masonry Paint",
        "Anti Mould Paint",
        "Damp Proof Paint",
    ]
    
    for category in categories:
        tokens = _category_required_tokens(category)
        print(f"\nCategory: '{category}'")
        print(f"Required tokens: {tokens}")


def test_token_matching():
    """Test that tokens are found in SKU text."""
    print("\n" + "=" * 80)
    print("TEST 3: Token Matching")
    print("=" * 80)
    
    test_cases = [
        {
            "category": "Anti Climb Paint",
            "sku_name": "Blackfriar Anti-Climb Paint Black",
            "expected": True
        },
        {
            "category": "Masonry Paint",
            "sku_name": "Bedec Multi Surface Paint (suitable for masonry)",
            "expected": True
        },
        {
            "category": "Masonry Paint",
            "sku_name": "Masonry Paint White",
            "expected": True
        },
    ]
    
    for test in test_cases:
        category = test["category"]
        sku_name = test["sku_name"]
        expected = test["expected"]
        
        required_tokens = _category_required_tokens(category)
        sku_normalized = _normalize_value(sku_name)
        tokens_present = _category_tokens_present(required_tokens, sku_normalized)
        
        status = "✓" if tokens_present == expected else "✗"
        print(f"\n{status} Category: '{category}'")
        print(f"   SKU: '{sku_name}'")
        print(f"   Required tokens: {required_tokens}")
        print(f"   SKU normalized: '{sku_normalized}'")
        print(f"   Tokens present: {tokens_present} (expected: {expected})")


def test_full_matching():
    """Test full SKU matching with actual data."""
    print("\n" + "=" * 80)
    print("TEST 4: Full SKU Matching")
    print("=" * 80)
    
    # Create test SKUs
    skus = [
        {
            "TS Product Code": "74796",
            "Product Brand Name": "Blackfriar",
            "Part Name": "Blackfriar Anti-Climb Paint Black",
            "Part Name Type": "1L",
            "Toolstation Web Copy": "Deter potential intruders with Blackfriar Anti-Climb Paint",
        },
        {
            "TS Product Code": "10734",
            "Product Brand Name": "Bedec",
            "Part Name": "Bedec Multi Surface Paint",
            "Part Name Type": "Gloss White 750ml",
            "Toolstation Web Copy": "Use on a variety of surfaces including wood, MDF, metals, plastics, tiles, masonry, plaster and uPVC.",
        },
        {
            "TS Product Code": "99999",
            "Product Brand Name": "Test",
            "Part Name": "Masonry Paint White",
            "Part Name Type": "5L",
            "Toolstation Web Copy": "Perfect for masonry surfaces",
        }
    ]
    
    df = pd.DataFrame(skus)
    df.to_csv('test_pim.csv', index=False)
    
    # Test categories
    category_facet_map = [
        {'Category Mapping': 'Anti Climb Paint', 'Facet Attribute': 'Root Category', 'Facet Value': 'Root Category'},
        {'Category Mapping': 'Masonry Paint', 'Facet Attribute': 'Root Category', 'Facet Value': 'Root Category'},
    ]
    
    print("\nRunning full analysis...")
    try:
        result = analyze_pim_skus('test_pim.csv', category_facet_map)
        
        print("\nResults:")
        for entry in result['category_facet_counts']:
            category = entry['Category Mapping']
            sku_count = entry['SKU Count']
            sku_ids = entry['SKU IDs']
            print(f"  {category}: {sku_count} SKUs - {sku_ids}")
            
            # Check if expected SKUs are matched
            if category == 'Anti Climb Paint':
                expected_sku = '74796'
                if expected_sku in sku_ids:
                    print(f"    ✓ Correctly matched SKU {expected_sku}")
                else:
                    print(f"    ✗ MISSING: Expected SKU {expected_sku} but got {sku_ids}")
            elif category == 'Masonry Paint':
                # Should match SKU 10734 (has masonry in description) or 99999 (has Masonry Paint in name)
                expected_skus = ['10734', '99999']
                matched_expected = [sku for sku in expected_skus if sku in sku_ids]
                if matched_expected:
                    print(f"    ✓ Matched expected SKUs: {matched_expected}")
                else:
                    print(f"    ✗ MISSING: Expected SKUs {expected_skus} but got {sku_ids}")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()


def test_intelligent_match():
    """Test the _intelligent_match function directly."""
    print("\n" + "=" * 80)
    print("TEST 5: Intelligent Match Function")
    print("=" * 80)
    
    test_cases = [
        {
            "target": "Masonry Paint",
            "sku_row": pd.Series({
                "Part Name": "Masonry Paint White",
                "Toolstation Web Copy": "Perfect for masonry"
            }),
            "sku_text": "Masonry Paint White Perfect for masonry",
            "columns": ["Part Name", "Toolstation Web Copy"],
            "expected": True
        },
        {
            "target": "Anti Climb Paint",
            "sku_row": pd.Series({
                "Part Name": "Blackfriar Anti-Climb Paint Black",
                "Toolstation Web Copy": "Deter potential intruders with Anti-Climb Paint"
            }),
            "sku_text": "Blackfriar Anti-Climb Paint Black Deter potential intruders",
            "columns": ["Part Name", "Toolstation Web Copy"],
            "expected": True
        }
    ]
    
    for test in test_cases:
        target = test["target"]
        sku_row = test["sku_row"]
        sku_text = test["sku_text"]
        columns = test["columns"]
        expected = test["expected"]
        
        # Create minimal knowledge base
        knowledge_base = {}
        
        result = _intelligent_match(
            target,
            sku_row,
            sku_text,
            columns,
            knowledge_base,
            match_type='category'
        )
        
        status = "✓" if result == expected else "✗"
        print(f"\n{status} Target: '{target}'")
        print(f"   SKU columns: {columns}")
        print(f"   Match result: {result} (expected: {expected})")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("SKU MATCHING DIAGNOSTIC TESTS")
    print("=" * 80)
    
    test_normalization()
    test_token_extraction()
    test_token_matching()
    test_intelligent_match()
    test_full_matching()
    
    print("\n" + "=" * 80)
    print("TESTS COMPLETE")
    print("=" * 80)

