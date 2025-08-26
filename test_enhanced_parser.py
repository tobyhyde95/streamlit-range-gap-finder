#!/usr/bin/env python3
"""
Test script for the enhanced URL parser functionality.
This demonstrates the improvements made to category extraction and facet normalization.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from seo_analyzer.url_parser import URLParser
from seo_analyzer.synonym_discovery import SynonymDiscovery


def test_category_extraction():
    """Test the enhanced category extraction functionality."""
    print("=== Testing Enhanced Category Extraction ===")
    
    url_parser = URLParser()
    
    # Test cases from the requirements
    test_urls = [
        "https://example.com/c/tools/drills/cat830704",
        "https://example.com/tools/drills/sds-drills?brand=dewalt",
        "https://example.com/c/power-tools/hammers/p-12345",
        "https://example.com/construction/tools/screwdrivers/12345",
        "https://example.com/diy/garden-tools/rakes"
    ]
    
    for url in test_urls:
        category = url_parser.extract_category_from_url(url)
        print(f"URL: {url}")
        print(f"  Extracted Category: {category}")
        print()


def test_facet_normalization():
    """Test the enhanced facet normalization functionality."""
    print("=== Testing Enhanced Facet Normalization ===")
    
    url_parser = URLParser()
    
    # Test cases from the requirements
    test_facets = [
        "Length (Mm)",
        "Screwlength",
        "diameter%20(mm)",
        "screwdiametermm",
        "brand%2Fname",
        "color%20option"
    ]
    
    for facet in test_facets:
        normalized = url_parser.normalize_facet_key(facet)
        print(f"Original: {facet}")
        print(f"  Normalized: {normalized}")
        print()


def test_synonym_discovery():
    """Test the synonym discovery functionality."""
    print("=== Testing Synonym Discovery ===")
    
    discovery = SynonymDiscovery()
    
    # Test URLs with potential synonyms
    test_urls = [
        "https://example.com/tools/drills?length_mm=100&screwlength=50",
        "https://example.com/tools/hammers?diameter_mm=20&screwdiametermm=15",
        "https://example.com/tools/saws?length%20(mm)=200&screwlength=75",
        "https://example.com/tools/wrenches?diameter%20(mm)=25&screwdiametermm=30"
    ]
    
    print("Discovering synonyms from test URLs...")
    candidates = discovery.discover_synonyms_from_urls(test_urls)
    
    if candidates:
        print(f"Found {len(candidates)} potential synonyms:")
        for candidate in candidates:
            print(f"  {candidate['new_term']} -> {candidate['suggested_mapping']} (confidence: {candidate['confidence_score']:.2f})")
        
        # Store candidates in database
        stored_ids = discovery.store_candidates(candidates)
        print(f"Stored {len(stored_ids)} candidates in database")
    else:
        print("No synonyms discovered (this is expected if no similar terms exist in the config)")


def test_config_management():
    """Test configuration management functionality."""
    print("=== Testing Configuration Management ===")
    
    url_parser = URLParser()
    
    # Test adding new synonyms
    print("Adding new category synonym...")
    url_parser.add_category_synonym("powertool", "power-tool")
    
    print("Adding new facet synonym...")
    url_parser.add_facet_synonym("tool_length", "length_mm")
    
    # Test the new synonyms
    test_url = "https://example.com/c/powertool/drills"
    category = url_parser.extract_category_from_url(test_url)
    print(f"URL with new synonym: {test_url}")
    print(f"  Extracted Category: {category}")
    
    normalized_facet = url_parser.normalize_facet_key("tool_length")
    print(f"Facet with new synonym: tool_length -> {normalized_facet}")


def main():
    """Run all tests."""
    print("Enhanced URL Parser and Synonym Discovery Test Suite")
    print("=" * 60)
    print()
    
    try:
        test_category_extraction()
        test_facet_normalization()
        test_synonym_discovery()
        test_config_management()
        
        print("=== Test Summary ===")
        print("✅ All tests completed successfully!")
        print()
        print("Key improvements demonstrated:")
        print("1. Enhanced category extraction with configurable identifier patterns")
        print("2. Improved facet normalization with URL decoding and synonym lookup")
        print("3. Synonym discovery system with Levenshtein distance calculation")
        print("4. Configuration management with JSON persistence")
        print()
        print("The system is now ready for integration with the full-stack application.")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
