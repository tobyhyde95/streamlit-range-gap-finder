"""
Test script for Smart SKU Counting and Classification Logic

This script validates the new weighted scoring system and depth vs. demand classification.
"""
import pandas as pd
import sys
import os

# Add the seo_analyzer directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'seo_analyzer'))

from pim_sku_analyzer import (
    _get_column_weight,
    _is_term_noisy,
    calculate_match_score_weighted,
    _calculate_sku_count_for_term_weighted,
    classify_term_by_depth_and_demand,
    COLUMN_WEIGHTS
)

def test_column_weights():
    """Test that column weights are assigned correctly."""
    print("\n=== Testing Column Weight Assignment ===")
    
    test_cases = [
        ("Part Name", COLUMN_WEIGHTS['high_confidence']),
        ("Part Name Type", COLUMN_WEIGHTS['high_confidence']),
        ("Product Brand Name", COLUMN_WEIGHTS['medium_confidence']),
        ("Finish", COLUMN_WEIGHTS['medium_confidence']),
        ("Application Method", COLUMN_WEIGHTS['medium_confidence']),
        ("Toolstation Web Copy", COLUMN_WEIGHTS['low_confidence']),
        ("Supplier Copy", COLUMN_WEIGHTS['low_confidence']),
        ("TS Product Code", COLUMN_WEIGHTS['ignore']),
    ]
    
    passed = 0
    for col_name, expected_weight in test_cases:
        actual_weight = _get_column_weight(col_name)
        status = "✓" if actual_weight == expected_weight else "✗"
        print(f"{status} {col_name}: {actual_weight} (expected {expected_weight})")
        if actual_weight == expected_weight:
            passed += 1
    
    print(f"\nPassed: {passed}/{len(test_cases)}")
    return passed == len(test_cases)


def test_noise_detection():
    """Test noise detection logic with and without pre-computed corpus."""
    print("\n=== Testing Noise Detection ===")
    
    # Create sample PIM data
    data = {
        'Part Name': ['Anti Mould Paint', 'Masonry Paint', 'Wood Paint', 'Metal Paint', 'Spray Paint'],
        'Description': [
            'Premium anti mould paint for bathrooms',
            'Durable masonry paint with spray application',
            'Exterior wood paint with spray nozzle',
            'Metal paint available in spray can',
            'Professional spray paint for all surfaces'
        ]
    }
    pim_df = pd.DataFrame(data)
    
    # Test WITHOUT pre-computed corpus (legacy mode)
    is_spray_noisy = _is_term_noisy(pim_df, 'spray', ['Description'], None)
    print(f"  'spray' is {'NOISY' if is_spray_noisy else 'SPECIFIC'} (expected NOISY)")
    
    # Test WITH pre-computed corpus (optimized mode)
    description_corpus = pim_df[['Description']].apply(lambda x: ' '.join(x.astype(str)), axis=1).str.lower()
    is_spray_noisy_optimized = _is_term_noisy(pim_df, 'spray', ['Description'], description_corpus)
    print(f"  'spray' (optimized) is {'NOISY' if is_spray_noisy_optimized else 'SPECIFIC'} (expected NOISY)")
    
    # Test "anti mould" - appears in 1/5 = 20% of descriptions, which is > 15% threshold
    is_anti_mould_noisy = _is_term_noisy(pim_df, 'anti mould', ['Description'], description_corpus)
    print(f"  'anti mould' is {'NOISY' if is_anti_mould_noisy else 'SPECIFIC'} (expected NOISY at 20%)")
    
    # Create a better test with more rows
    data2 = {
        'Part Name': ['Anti Mould Paint'] + ['Other Product'] * 19,
        'Description': ['Premium anti mould paint'] + ['Generic description'] * 19
    }
    pim_df2 = pd.DataFrame(data2)
    description_corpus2 = pim_df2[['Description']].apply(lambda x: ' '.join(x.astype(str)), axis=1).str.lower()
    
    # Now "anti mould" appears in 1/20 = 5% of descriptions - should be SPECIFIC
    is_anti_mould_specific = _is_term_noisy(pim_df2, 'anti mould', ['Description'], description_corpus2)
    print(f"  'anti mould' (1/20 rows) is {'NOISY' if is_anti_mould_specific else 'SPECIFIC'} (expected SPECIFIC at 5%)")
    
    # Verify both methods produce the same result
    return (is_spray_noisy and is_spray_noisy_optimized and 
            is_anti_mould_noisy and not is_anti_mould_specific)


def test_weighted_scoring():
    """Test weighted match scoring."""
    print("\n=== Testing Weighted Match Scoring ===")
    
    # Create a sample SKU row
    row = pd.Series({
        'Part Name': 'Anti Mould Paint 5L White',
        'Product Brand Name': 'Ronseal',
        'Description': 'This masonry paint contains spray nozzle for easy application'
    })
    
    column_weights = {
        'Part Name': COLUMN_WEIGHTS['high_confidence'],
        'Product Brand Name': COLUMN_WEIGHTS['medium_confidence'],
        'Description': COLUMN_WEIGHTS['low_confidence']
    }
    
    description_columns = {'Description'}
    
    # Test 1: Specific term "Anti Mould" (not noisy)
    # Should match in Part Name (10 pts) = 10 total
    score1 = calculate_match_score_weighted(row, 'Anti Mould', False, column_weights, description_columns)
    print(f"  Score for 'Anti Mould' (not noisy): {score1} (expected 10)")
    
    # Test 2: Noisy term "spray" (noisy = True)
    # Should match in Description but be ignored (0 pts) = 0 total
    score2 = calculate_match_score_weighted(row, 'spray', True, column_weights, description_columns)
    print(f"  Score for 'spray' (noisy): {score2} (expected 0)")
    
    # Test 3: Noisy term "spray" (not noisy)
    # Should match in Description (1 pt) = 1 total
    score3 = calculate_match_score_weighted(row, 'spray', False, column_weights, description_columns)
    print(f"  Score for 'spray' (not noisy): {score3} (expected 1)")
    
    return score1 == 10 and score2 == 0 and score3 == 1


def test_classification_logic():
    """Test depth vs. demand classification."""
    print("\n=== Testing Classification Logic ===")
    
    test_cases = [
        (50, 500, "Core Category"),      # SKU >= 40
        (100, 2000, "Core Category"),    # SKU >= 40
        (30, 1500, "SEO Landing Page"),  # SKU < 40, Traffic >= 1000
        (20, 500, "Facet / Filter"),     # SKU < 40, Traffic < 1000
        (0, 100, "Facet / Filter"),      # SKU < 40, Traffic < 1000
    ]
    
    passed = 0
    for sku_count, traffic, expected in test_cases:
        result = classify_term_by_depth_and_demand(sku_count, traffic)
        status = "✓" if result == expected else "✗"
        print(f"{status} SKU={sku_count}, Traffic={traffic}: '{result}' (expected '{expected}')")
        if result == expected:
            passed += 1
    
    print(f"\nPassed: {passed}/{len(test_cases)}")
    return passed == len(test_cases)


def test_end_to_end_sku_counting():
    """Test end-to-end SKU counting with realistic data and optimized corpus."""
    print("\n=== Testing End-to-End SKU Counting ===")
    
    # Create realistic PIM data
    data = {
        'TS Product Code': ['SKU001', 'SKU002', 'SKU003', 'SKU004', 'SKU005'],
        'Part Name': [
            'Anti Mould Paint 5L White',
            'Masonry Paint 10L Grey',
            'Wood Stain 2.5L Oak',
            'Metal Paint 1L Black',
            'Spray Paint 400ml Red'
        ],
        'Product Brand Name': ['Ronseal', 'Dulux', 'Cuprinol', 'Hammerite', 'Rust-Oleum'],
        'Toolstation Web Copy': [
            'Premium anti mould paint perfect for bathrooms. Contains spray applicator.',
            'Durable masonry paint for exterior walls. Available with spray gun option.',
            'Beautiful wood stain for outdoor furniture. Can be applied with spray.',
            'Protective metal paint with rust prevention. Spray application available.',
            'Professional spray paint for all surfaces. Quick-drying formula.'
        ]
    }
    
    df = pd.DataFrame(data)
    
    # Pre-compute description corpus (simulating the optimization)
    description_corpus = df[['Toolstation Web Copy']].apply(
        lambda x: ' '.join(x.astype(str)), axis=1
    ).str.lower()
    
    # Test 1: Count "Anti Mould" (specific term) - with optimized corpus
    count1 = _calculate_sku_count_for_term_weighted(df, 'Anti Mould', 'TS Product Code', description_corpus)
    print(f"  'Anti Mould' SKU Count: {count1} (expected 1)")
    
    # Test 2: Count "spray" (noisy term - appears in 5/5 descriptions = 100%)
    count2 = _calculate_sku_count_for_term_weighted(df, 'spray', 'TS Product Code', description_corpus)
    print(f"  'spray' SKU Count: {count2} (expected 1, only SKU005)")
    
    # Test 3: Count "Paint" (should match multiple SKUs)
    count3 = _calculate_sku_count_for_term_weighted(df, 'Paint', 'TS Product Code', description_corpus)
    print(f"  'Paint' SKU Count: {count3} (expected 4-5)")
    
    # Test 4: Verify performance - test without corpus (legacy mode)
    print("\n  Testing legacy mode (without pre-computed corpus)...")
    count1_legacy = _calculate_sku_count_for_term_weighted(df, 'Anti Mould', 'TS Product Code', None)
    print(f"  'Anti Mould' SKU Count (legacy): {count1_legacy} (should match optimized: {count1})")
    
    return count1 == 1 and count2 == 1 and count1 == count1_legacy


def main():
    """Run all tests."""
    print("=" * 60)
    print("SMART SKU COUNTING - TEST SUITE")
    print("=" * 60)
    
    results = {
        "Column Weights": test_column_weights(),
        "Noise Detection": test_noise_detection(),
        "Weighted Scoring": test_weighted_scoring(),
        "Classification Logic": test_classification_logic(),
        "End-to-End SKU Counting": test_end_to_end_sku_counting()
    }
    
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{status}: {test_name}")
    
    all_passed = all(results.values())
    print("\n" + ("=" * 60))
    if all_passed:
        print("✓ ALL TESTS PASSED")
    else:
        print("✗ SOME TESTS FAILED")
    print("=" * 60)
    
    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())

