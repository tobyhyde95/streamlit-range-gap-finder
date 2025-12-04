"""
Performance Test: Demonstrates the impact of pre-computing the description corpus

This test shows the dramatic performance improvement when analyzing multiple terms.
"""
import pandas as pd
import time
import sys
import os

# Add the seo_analyzer directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'seo_analyzer'))

from pim_sku_analyzer import _is_term_noisy, _get_column_weight, COLUMN_WEIGHTS


def create_large_pim_dataset(num_rows=1000):
    """Create a realistic large PIM dataset for performance testing."""
    print(f"Creating test dataset with {num_rows} SKUs...")
    
    # Generate realistic product data
    products = []
    for i in range(num_rows):
        product_type = ['Paint', 'Stain', 'Varnish', 'Primer', 'Sealer'][i % 5]
        color = ['White', 'Black', 'Grey', 'Red', 'Blue', 'Green'][i % 6]
        size = ['1L', '2.5L', '5L', '10L'][i % 4]
        
        products.append({
            'TS Product Code': f'SKU{i:05d}',
            'Part Name': f'{product_type} {size} {color}',
            'Product Brand Name': ['Dulux', 'Ronseal', 'Cuprinol', 'Hammerite'][i % 4],
            'Toolstation Web Copy': f'Professional {product_type.lower()} for interior and exterior use. Available in spray and brush application. Durable finish with excellent coverage.',
            'Supplier Copy': f'High quality {product_type.lower()} suitable for wood, metal, and masonry surfaces. Quick drying formula.'
        })
    
    return pd.DataFrame(products)


def test_performance_without_optimization(pim_df, terms, description_columns):
    """Test performance WITHOUT pre-computed corpus (legacy mode)."""
    print("\n=== Testing WITHOUT Optimization (Legacy Mode) ===")
    print(f"Analyzing {len(terms)} terms against {len(pim_df)} SKUs...")
    
    start_time = time.time()
    
    results = {}
    for term in terms:
        # Call without pre-computed corpus (forces row-by-row iteration each time)
        is_noisy = _is_term_noisy(pim_df, term, description_columns, None)
        results[term] = is_noisy
    
    elapsed_time = time.time() - start_time
    
    print(f"✗ Completed in {elapsed_time:.2f} seconds")
    print(f"  Average: {elapsed_time / len(terms):.3f} seconds per term")
    
    return elapsed_time, results


def test_performance_with_optimization(pim_df, terms, description_columns):
    """Test performance WITH pre-computed corpus (optimized mode)."""
    print("\n=== Testing WITH Optimization (Pre-computed Corpus) ===")
    print(f"Analyzing {len(terms)} terms against {len(pim_df)} SKUs...")
    
    start_time = time.time()
    
    # Pre-compute description corpus ONCE
    print("Pre-computing description corpus...")
    corpus_start = time.time()
    description_corpus = pim_df[description_columns].apply(
        lambda x: ' '.join(x.astype(str)), axis=1
    ).str.lower()
    corpus_time = time.time() - corpus_start
    print(f"  Corpus computed in {corpus_time:.3f} seconds")
    
    # Now analyze all terms using the pre-computed corpus
    analysis_start = time.time()
    results = {}
    for term in terms:
        # Call with pre-computed corpus (vectorized operation, no row iteration!)
        is_noisy = _is_term_noisy(pim_df, term, description_columns, description_corpus)
        results[term] = is_noisy
    analysis_time = time.time() - analysis_start
    
    total_time = time.time() - start_time
    
    print(f"✓ Completed in {total_time:.2f} seconds")
    print(f"  Corpus creation: {corpus_time:.3f} seconds")
    print(f"  Analysis: {analysis_time:.3f} seconds")
    print(f"  Average: {analysis_time / len(terms):.3f} seconds per term")
    
    return total_time, results


def main():
    """Run performance comparison."""
    print("=" * 70)
    print("PERFORMANCE TEST: Pre-computed Corpus Optimization")
    print("=" * 70)
    
    # Create test dataset
    num_skus = 500  # Realistic PIM export size
    pim_df = create_large_pim_dataset(num_skus)
    
    # Identify description columns
    all_columns = pim_df.columns.tolist()
    description_columns = [col for col in all_columns if _get_column_weight(col) == COLUMN_WEIGHTS['low_confidence']]
    print(f"Description columns: {description_columns}")
    
    # Test terms (realistic taxonomy analysis scenario)
    terms = [
        'Paint', 'Spray Paint', 'White Paint', 'Exterior Paint',
        'Anti Mould', 'Low VOC', 'Quick Drying', 'Durable',
        'Wood Stain', 'Metal Paint', 'Masonry Paint', 'Primer',
        'Varnish', 'Sealer', 'Gloss', 'Matt', 'Satin',
        'Interior', 'Exterior', 'Professional'
    ]
    
    print(f"\nTest scenario: {len(terms)} terms × {num_skus} SKUs = {len(terms) * num_skus:,} comparisons")
    
    # Test WITHOUT optimization
    time_without, results_without = test_performance_without_optimization(
        pim_df, terms, description_columns
    )
    
    # Test WITH optimization
    time_with, results_with = test_performance_with_optimization(
        pim_df, terms, description_columns
    )
    
    # Verify results are identical
    print("\n=== Verification ===")
    results_match = results_without == results_with
    print(f"Results match: {'✓ YES' if results_match else '✗ NO'}")
    
    if not results_match:
        print("WARNING: Results differ between optimized and legacy modes!")
        for term in terms:
            if results_without[term] != results_with[term]:
                print(f"  '{term}': Legacy={results_without[term]}, Optimized={results_with[term]}")
    
    # Calculate performance improvement
    print("\n" + "=" * 70)
    print("PERFORMANCE SUMMARY")
    print("=" * 70)
    print(f"Legacy mode:    {time_without:.2f} seconds")
    print(f"Optimized mode: {time_with:.2f} seconds")
    
    speedup = time_without / time_with if time_with > 0 else 0
    time_saved = time_without - time_with
    percent_faster = ((time_without - time_with) / time_without * 100) if time_without > 0 else 0
    
    print(f"\n✓ Speedup: {speedup:.1f}x faster")
    print(f"✓ Time saved: {time_saved:.2f} seconds ({percent_faster:.0f}% reduction)")
    
    # Extrapolate to realistic scenarios
    print("\n" + "=" * 70)
    print("REAL-WORLD IMPACT")
    print("=" * 70)
    
    # Scenario 1: 500 terms (large taxonomy analysis)
    large_terms = 500
    legacy_time_large = (time_without / len(terms)) * large_terms
    optimized_time_large = (time_with / len(terms)) * large_terms
    
    print(f"\nScenario: {large_terms} terms × {num_skus} SKUs")
    print(f"  Legacy mode:    {legacy_time_large:.0f} seconds ({legacy_time_large/60:.1f} minutes)")
    print(f"  Optimized mode: {optimized_time_large:.0f} seconds ({optimized_time_large/60:.1f} minutes)")
    print(f"  Time saved:     {legacy_time_large - optimized_time_large:.0f} seconds ({(legacy_time_large - optimized_time_large)/60:.1f} minutes)")
    
    print("\n" + "=" * 70)
    
    if results_match and speedup > 1:
        print("✓ OPTIMIZATION SUCCESSFUL")
        print("  - Results are identical")
        print(f"  - Performance improved by {speedup:.1f}x")
        print("  - No functional regressions detected")
        return 0
    else:
        print("✗ OPTIMIZATION FAILED")
        return 1


if __name__ == '__main__':
    sys.exit(main())

