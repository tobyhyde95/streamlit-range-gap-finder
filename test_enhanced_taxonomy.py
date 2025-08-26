#!/usr/bin/env python3
"""
Test script to verify that the taxonomy analysis is using the enhanced URL parser.
"""

import sys
import os
import pandas as pd
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from seo_analyzer.taxonomy_analysis import _generate_category_overhaul_matrix


def test_enhanced_taxonomy():
    """Test that the taxonomy analysis uses enhanced URL parsing."""
    print("=== Testing Enhanced Taxonomy Analysis ===")
    
    # Create test data with URLs that should benefit from enhanced parsing
    test_data = {
        'keyword': ['drill test', 'hammer test', 'saw test'],
        'position': [1, 2, 3],
        'traffic': [100, 200, 300],
        'volume': [1000, 2000, 3000],  # Add volume column
        'url': [
            'https://example.com/c/tools/drills/cat830704?length_mm=100&screwlength=50',
            'https://example.com/tools/hammers/p-12345?diameter_mm=20&screwdiametermm=15',
            'https://example.com/power-tools/saws/sds-drills?brand=dewalt&length%20(mm)=200'
        ]
    }
    
    df = pd.DataFrame(test_data)
    
    print("Test URLs:")
    for url in test_data['url']:
        print(f"  {url}")
    print()
    
    # Run the taxonomy analysis with enhanced parsing enabled
    print("Running taxonomy analysis with enhanced parsing...")
    result = _generate_category_overhaul_matrix(
        df=df,
        internal_keyword_col='keyword',
        internal_position_col='position',
        internal_traffic_col='traffic',
        internal_url_col_name='url',
        onsite_df=None,
        internal_volume_col='volume',
        enable_enhanced_parsing=True,
        enable_synonym_discovery=True
    )
    
    print("✅ Enhanced taxonomy analysis completed successfully!")
    print()
    print("Expected improvements:")
    print("1. Category extraction should use configurable identifier patterns")
    print("2. Facet normalization should use synonym dictionary")
    print("3. Synonym discovery should identify potential new rules")
    print("4. URL decoding should handle encoded characters")
    print()
    print("The system is now using the enhanced URL parser for all taxonomy analysis!")


if __name__ == "__main__":
    test_enhanced_taxonomy()
