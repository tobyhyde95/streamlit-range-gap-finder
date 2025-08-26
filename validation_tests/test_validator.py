#!/usr/bin/env python3
"""
Simple test script to demonstrate the Category Mapping Validator.
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from category_mapping_validator import validate_category_overhaul_matrix_automation

def create_sample_data():
    """Create sample data for testing."""
    return [
        {
            "Category Mapping": "decking-screws",
            "url": "https://www.screwfix.com/c/screws-nails-fixings/decking-screws/cat840048",
            "keyword": "decking screws",
            "monthlyOrganicTraffic": 3273
        },
        {
            "Category Mapping": "concrete-screws", 
            "url": "https://www.screwfix.com/c/screws-nails-fixings/concrete-screws/cat840054",
            "keyword": "masonry screws",
            "monthlyOrganicTraffic": 2619
        },
        {
            "Category Mapping": "security-screws",
            "url": "https://www.screwfix.com/c/screws-nails-fixings/security-screws/cat840238", 
            "keyword": "security screws",
            "monthlyOrganicTraffic": 3114
        }
    ]

def main():
    """Run a simple validation test."""
    print("🧪 Testing Category Mapping Validator")
    print("=" * 40)
    
    # Create sample data
    sample_data = create_sample_data()
    print(f"📊 Created {len(sample_data)} sample rows")
    
    # Run validation
    print("\n🔍 Running validation...")
    results = validate_category_overhaul_matrix_automation(sample_data)
    
    # Display results
    summary = results['summary']
    print(f"\n✅ Validation complete!")
    print(f"   Accuracy: {summary['accuracy_percentage']}%")
    print(f"   Correct: {summary['correct_mappings']}/{summary['total_rows']}")
    
    if summary['common_issues']:
        print(f"\n⚠️  Issues found:")
        for issue, count in summary['common_issues'].items():
            print(f"   • {issue}: {count} occurrences")
    else:
        print(f"\n🎉 No issues found!")

if __name__ == "__main__":
    main()
