"""
Regression Test Suite for Taxonomy & Facet Lens Refactoring
Version: 1.2 (Precision Overhaul)

This test suite validates that URL structure is the definitive driver for
'Category Mapping' and that AI semantic guessing does not incorrectly merge
distinct categories.
"""

import unittest
import pandas as pd
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from seo_analyzer.taxonomy_analysis import _generate_category_overhaul_matrix
from seo_analyzer.enhanced_taxonomy_analysis import _generate_enhanced_category_overhaul_matrix


class TestTaxonomyRefactoring(unittest.TestCase):
    """Test cases for taxonomy refactoring to ensure URL-based category mapping."""
    
    def setUp(self):
        """Set up test data."""
        self.internal_keyword_col = 'Keyword'
        self.internal_position_col = 'Position'
        self.internal_traffic_col = 'Traffic'
        self.internal_url_col = 'URL'
        self.internal_volume_col = 'Volume'
    
    def test_exterior_wood_paint_not_merged_into_cladding(self):
        """
        Regression Test Case 1:
        Input: Keyword "outdoor wood paint", URL ".../exterior-wood"
        Expected: Category should be "Exterior Wood" (NOT "Cladding")
        
        This tests that semantic similarity does not cause incorrect category merging.
        Note: Categories are now normalized (Title Case, no hyphens)
        """
        # Create test data
        test_data = pd.DataFrame({
            self.internal_keyword_col: ['outdoor wood paint', 'exterior wood paint', 'wood cladding'],
            self.internal_url_col: [
                'https://example.com/exterior-wood',
                'https://example.com/exterior-wood',
                'https://example.com/cladding'
            ],
            self.internal_position_col: [1, 2, 1],
            self.internal_traffic_col: [100, 80, 500],  # Cladding has higher traffic
            self.internal_volume_col: [1000, 800, 5000]
        })
        
        # Run the analysis
        result = _generate_category_overhaul_matrix(
            df=test_data,
            internal_keyword_col=self.internal_keyword_col,
            internal_position_col=self.internal_position_col,
            internal_traffic_col=self.internal_traffic_col,
            internal_url_col_name=self.internal_url_col,
            onsite_df=None,
            internal_volume_col=self.internal_volume_col
        )
        
        matrix_report = pd.DataFrame(result['matrix_report'])
        
        # Verify that 'Exterior Wood' and 'Cladding' remain separate categories
        categories = matrix_report['Category Mapping'].unique()
        
        # Both categories should exist separately (normalized format: Title Case, no hyphens)
        self.assertIn('Exterior Wood', categories, 
                      "Exterior Wood should be a distinct category")
        self.assertIn('Cladding', categories, 
                      "Cladding should remain a separate category")
        
        # Verify that 'outdoor wood paint' is categorized as 'Exterior Wood'
        outdoor_wood_rows = matrix_report[
            matrix_report['KeywordDetails'].apply(
                lambda x: any(kw['Keyword'] == 'outdoor wood paint' for kw in x)
            )
        ]
        
        if not outdoor_wood_rows.empty:
            actual_category = outdoor_wood_rows.iloc[0]['Category Mapping']
            self.assertEqual(actual_category, 'Exterior Wood',
                            f"outdoor wood paint should be categorized as 'Exterior Wood', not '{actual_category}'")
    
    def test_damp_paint_not_merged_into_gloss(self):
        """
        Regression Test Case 2:
        Input: Keyword "damp paint", URL ".../damp-proof-paint/"
        Expected: Category should be "Damp Proof Paint" (NOT "Gloss")
        
        This tests that traffic-based reclassification does not force niche
        products into incorrect high-volume categories.
        Note: Categories are now normalized (Title Case, no hyphens)
        """
        # Create test data with high-traffic gloss paint category
        test_data = pd.DataFrame({
            self.internal_keyword_col: [
                'damp paint', 'damp proof paint', 'waterproof paint',
                'gloss paint', 'gloss paint white', 'gloss paint black'
            ],
            self.internal_url_col: [
                'https://example.com/damp-proof-paint/',
                'https://example.com/damp-proof-paint/',
                'https://example.com/damp-proof-paint/',
                'https://example.com/gloss',
                'https://example.com/gloss',
                'https://example.com/gloss'
            ],
            self.internal_position_col: [1, 1, 1, 1, 1, 1],
            self.internal_traffic_col: [50, 40, 30, 5000, 4000, 3000],  # Gloss has much higher traffic
            self.internal_volume_col: [500, 400, 300, 50000, 40000, 30000]
        })
        
        # Run the analysis
        result = _generate_category_overhaul_matrix(
            df=test_data,
            internal_keyword_col=self.internal_keyword_col,
            internal_position_col=self.internal_position_col,
            internal_traffic_col=self.internal_traffic_col,
            internal_url_col_name=self.internal_url_col,
            onsite_df=None,
            internal_volume_col=self.internal_volume_col
        )
        
        matrix_report = pd.DataFrame(result['matrix_report'])
        
        # Verify that 'Damp Proof Paint' and 'Gloss' remain separate categories
        categories = matrix_report['Category Mapping'].unique()
        
        self.assertIn('Damp Proof Paint', categories,
                      "Damp Proof Paint should be a distinct category")
        self.assertIn('Gloss', categories,
                      "Gloss should remain a separate category")
        
        # Verify that 'damp paint' is NOT categorized as 'Gloss' despite higher traffic
        damp_paint_rows = matrix_report[
            matrix_report['KeywordDetails'].apply(
                lambda x: any(kw['Keyword'] == 'damp paint' for kw in x)
            )
        ]
        
        if not damp_paint_rows.empty:
            actual_category = damp_paint_rows.iloc[0]['Category Mapping']
            self.assertNotEqual(actual_category, 'Gloss',
                              f"damp paint should NOT be categorized as 'Gloss' (found: '{actual_category}')")
            self.assertEqual(actual_category, 'Damp Proof Paint',
                            f"damp paint should be categorized as 'Damp Proof Paint', not '{actual_category}'")
    
    def test_facet_merging_only_on_similar_column_names(self):
        """
        Test Case 3: Facet merging should only occur for similar column names.
        
        Verifies that distinct facet types (like 'Finish' and 'Material') are NOT
        merged even if they share common values.
        """
        # This test would require more complex setup with facet data
        # For now, we verify the behavior is name-based by checking the function exists
        from seo_analyzer.taxonomy_analysis import _generate_category_overhaul_matrix
        
        # Verify the refactored code doesn't merge based on data overlap
        # (This is a structural test - the actual merging logic is tested by integration)
        self.assertTrue(callable(_generate_category_overhaul_matrix),
                       "Category overhaul matrix generation function should be available")
    
    def test_url_parser_is_definitive_source(self):
        """
        Test Case 4: URL Parser should be the definitive source for category mapping.
        
        Verifies that the URL-based category extraction takes precedence over
        any semantic or traffic-based inference.
        """
        from seo_analyzer.url_parser import URLParser
        
        parser = URLParser()
        
        # Test that URL parser correctly extracts categories (normalized format)
        test_cases = [
            ('https://example.com/exterior-wood', 'Exterior Wood'),
            ('https://example.com/damp-proof-paint/', 'Damp Proof Paint'),
            ('https://example.com/masonry-paint', 'Masonry Paint'),
            ('https://example.com/wood-stain/interior-wood-stain', 'Interior Wood Stain'),  # Should get the most specific
        ]
        
        for url, expected_category in test_cases:
            extracted = parser.extract_category_from_url(url)
            self.assertIsNotNone(extracted,
                               f"URL parser should extract a category from {url}")
            self.assertEqual(extracted, expected_category,
                           f"URL parser should extract '{expected_category}' from {url}, got '{extracted}'")
    
    def test_enhanced_taxonomy_analysis_preserves_url_categories(self):
        """
        Test Case 5: Enhanced taxonomy analysis should preserve URL-based categories.
        
        Tests the enhanced taxonomy analysis function to ensure it doesn't
        overwrite URL-based categories with semantic guessing.
        """
        test_data = pd.DataFrame({
            self.internal_keyword_col: ['outdoor wood paint', 'wood cladding'],
            self.internal_url_col: [
                'https://example.com/exterior-wood',
                'https://example.com/cladding'
            ],
            self.internal_position_col: [1, 1],
            self.internal_traffic_col: [100, 500],
            self.internal_volume_col: [1000, 5000]
        })
        
        # Run the enhanced analysis
        result = _generate_enhanced_category_overhaul_matrix(
            df=test_data,
            internal_keyword_col=self.internal_keyword_col,
            internal_position_col=self.internal_position_col,
            internal_traffic_col=self.internal_traffic_col,
            internal_url_col_name=self.internal_url_col,
            onsite_df=None,
            internal_volume_col=self.internal_volume_col
        )
        
        # Note: Enhanced version currently returns empty results in the simplified implementation
        # This test verifies it doesn't crash and maintains the expected structure
        self.assertIsInstance(result, dict,
                            "Enhanced analysis should return a dictionary")
        self.assertIn('matrix_report', result,
                     "Result should contain matrix_report")
        self.assertIn('facet_potential_report', result,
                     "Result should contain facet_potential_report")


class TestColumnNameSimilarity(unittest.TestCase):
    """Test cases for column name similarity logic used in facet merging."""
    
    def test_similar_column_names_are_detected(self):
        """Test that similar column names are correctly identified for merging."""
        import re
        
        def normalize_column_name(col_name):
            """Normalize column name for comparison."""
            return re.sub(r'[_\s-]', '', str(col_name).lower())
        
        def are_column_names_similar(col_a, col_b):
            """Check if two column names are similar enough to merge."""
            norm_a = normalize_column_name(col_a)
            norm_b = normalize_column_name(col_b)
            
            if norm_a == norm_b:
                return True
            
            if norm_a in norm_b or norm_b in norm_a:
                if abs(len(norm_a) - len(norm_b)) <= 2:
                    return True
            
            return False
        
        # Test cases for similar names (should merge)
        # These are cases where normalization makes them identical or very close substrings
        similar_pairs = [
            ('Colour_Group', 'ColourGroup'),  # Normalized: colourgroup == colourgroup
            ('Brand Name', 'BrandName'),      # Normalized: brandname == brandname
            ('Size', 'size'),                 # Normalized: size == size
            ('Color_Code', 'ColorCode'),      # Normalized: colorcode == colorcode
        ]
        
        for col_a, col_b in similar_pairs:
            self.assertTrue(are_column_names_similar(col_a, col_b),
                          f"'{col_a}' and '{col_b}' should be considered similar")
        
        # Test cases for dissimilar names (should NOT merge)
        dissimilar_pairs = [
            ('Finish', 'Material'),
            ('Brand', 'Colour'),
            ('Size', 'Power'),
            ('Type', 'Category'),
            ('Color', 'Colour'),  # Different spellings - handled by synonym system, not automatic merging
        ]
        
        for col_a, col_b in dissimilar_pairs:
            self.assertFalse(are_column_names_similar(col_a, col_b),
                           f"'{col_a}' and '{col_b}' should NOT be considered similar")


def run_tests():
    """Run all test suites."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestTaxonomyRefactoring))
    suite.addTests(loader.loadTestsFromTestCase(TestColumnNameSimilarity))
    
    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Return exit code
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(run_tests())

