#!/usr/bin/env python3
"""
Category Mapping Validator

This module automatically validates the category mapping logic in Category Overhaul Matrix analysis.
It analyzes each unique row in the output and verifies that the URL-to-category mapping is working correctly.
"""

import json
import os
import pandas as pd
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from urllib.parse import urlparse
try:
    from .url_parser import URLParser
except ImportError:
    try:
        from url_parser import URLParser
    except ImportError:
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'seo_analyzer'))
        from url_parser import URLParser


class CategoryMappingValidator:
    """Validates category mapping logic in Category Overhaul Matrix analysis."""
    
    def __init__(self, output_dir: str = "validation_tests/TEST RESULTS"):
        """
        Initialize the validator.
        
        Args:
            output_dir: Directory to save validation reports
        """
        self.output_dir = output_dir
        self.url_parser = URLParser()
        
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
    
    def validate_category_overhaul_matrix(self, matrix_data: List[Dict], analysis_timestamp: str = None) -> Dict:
        """
        Validate the category mapping logic in a Category Overhaul Matrix.
        
        Args:
            matrix_data: The Category Overhaul Matrix data
            analysis_timestamp: Timestamp of the analysis (optional)
            
        Returns:
            Validation results dictionary
        """
        if not matrix_data:
            return {
                "status": "error",
                "message": "No matrix data provided",
                "validation_results": []
            }
        
        print("🔍 Starting Category Mapping Validation...")
        
        # Extract unique rows for validation
        unique_rows = self._extract_unique_rows(matrix_data)
        
        # Validate each unique row
        validation_results = []
        total_rows = len(unique_rows)
        
        for i, row in enumerate(unique_rows, 1):
            if i % 10 == 0:
                print(f"   Validating row {i}/{total_rows}...")
            
            result = self._validate_single_row(row)
            validation_results.append(result)
        
        # Generate summary statistics
        summary = self._generate_validation_summary(validation_results)
        
        # Create validation report
        validation_report = {
            "validation_timestamp": datetime.now().isoformat(),
            "analysis_timestamp": analysis_timestamp,
            "total_rows_validated": total_rows,
            "summary": summary,
            "validation_results": validation_results
        }
        
        # Save validation report
        self._save_validation_report(validation_report)
        
        print(f"✅ Category Mapping Validation Complete!")
        print(f"   📊 Results: {summary['correct_mappings']}/{total_rows} correct mappings")
        print(f"   📁 Report saved to: {self._get_validation_report_path()}")
        
        return validation_report
    
    def _extract_unique_rows(self, matrix_data: List[Dict]) -> List[Dict]:
        """
        Extract unique rows from matrix data based on Category Mapping and URL patterns.
        
        Args:
            matrix_data: The matrix data
            
        Returns:
            List of unique rows
        """
        unique_rows = []
        seen_combinations = set()
        
        for row in matrix_data:
            category_mapping = row.get('Category Mapping', '')
            url = row.get('url', '')
            
            # Create a unique key based on category mapping and URL pattern
            url_pattern = self._extract_url_pattern(url)
            combination_key = f"{category_mapping}|{url_pattern}"
            
            if combination_key not in seen_combinations:
                seen_combinations.add(combination_key)
                unique_rows.append(row)
        
        return unique_rows
    
    def _extract_url_pattern(self, url: str) -> str:
        """
        Extract a URL pattern for comparison (removes query parameters and specific IDs).
        
        Args:
            url: The URL to process
            
        Returns:
            URL pattern string
        """
        try:
            parsed = urlparse(url)
            path_parts = parsed.path.strip('/').split('/')
            
            # Remove category IDs and keep the structure
            pattern_parts = []
            for part in path_parts:
                if not self._is_category_id(part):
                    pattern_parts.append(part)
            
            return '/'.join(pattern_parts)
        except Exception:
            return url
    
    def _is_category_id(self, segment: str) -> bool:
        """
        Check if a URL segment is a category ID.
        
        Args:
            segment: URL segment to check
            
        Returns:
            True if it's a category ID
        """
        # Common category ID patterns
        id_patterns = [
            r'^cat\d+$',  # cat840048
            r'^c\d+$',    # c74
            r'^p-\d+$',   # p-12345
            r'^\d+$',     # 12345
        ]
        
        import re
        for pattern in id_patterns:
            if re.match(pattern, segment, re.IGNORECASE):
                return True
        
        return False
    
    def _validate_single_row(self, row: Dict) -> Dict:
        """
        Validate a single row's category mapping.
        
        Args:
            row: The row to validate
            
        Returns:
            Validation result dictionary
        """
        url = row.get('url', '')
        category_mapping = row.get('Category Mapping', '')
        keyword = row.get('keyword', '')
        
        # Extract expected category from URL
        expected_category = self.url_parser.extract_category_from_url(url)
        
        # Determine if mapping is correct
        is_correct = expected_category == category_mapping
        
        # Analyze the URL structure
        url_analysis = self._analyze_url_structure(url)
        
        # Determine the issue if mapping is incorrect
        issue = None
        if not is_correct:
            issue = self._identify_mapping_issue(url, category_mapping, expected_category)
        
        return {
            "row_data": {
                "keyword": keyword,
                "url": url,
                "category_mapping": category_mapping,
                "expected_category": expected_category
            },
            "validation": {
                "is_correct": is_correct,
                "issue": issue
            },
            "url_analysis": url_analysis
        }
    
    def _analyze_url_structure(self, url: str) -> Dict:
        """
        Analyze the structure of a URL to understand the category hierarchy.
        
        Args:
            url: The URL to analyze
            
        Returns:
            URL analysis dictionary
        """
        try:
            parsed = urlparse(url)
            path_parts = parsed.path.strip('/').split('/')
            
            # Identify different parts of the URL
            analysis = {
                "domain": parsed.netloc,
                "path_parts": path_parts,
                "category_hierarchy": [],
                "category_ids": [],
                "query_parameters": dict(parsed.query.split('&')) if parsed.query else {}
            }
            
            for part in path_parts:
                if self._is_category_id(part):
                    analysis["category_ids"].append(part)
                elif len(part) > 2 and any(c.isalpha() for c in part):
                    analysis["category_hierarchy"].append(part)
            
            return analysis
        except Exception as e:
            return {
                "error": str(e),
                "url": url
            }
    
    def _identify_mapping_issue(self, url: str, actual_mapping: str, expected_mapping: str) -> str:
        """
        Identify the specific issue with the category mapping.
        
        Args:
            url: The URL
            actual_mapping: The actual category mapping
            expected_mapping: The expected category mapping
            
        Returns:
            Description of the issue
        """
        if not expected_mapping:
            return "No category could be extracted from URL"
        
        if not actual_mapping:
            return "No category mapping found in row"
        
        # Check if it's a parent vs child category issue
        url_parts = urlparse(url).path.strip('/').split('/')
        human_readable_parts = [part for part in url_parts if not self._is_category_id(part) and len(part) > 2]
        
        if len(human_readable_parts) >= 2:
            parent_category = human_readable_parts[0]
            child_category = human_readable_parts[1]
            
            if actual_mapping == parent_category and expected_mapping == child_category:
                return f"Extracted parent category '{parent_category}' instead of child category '{child_category}'"
            elif actual_mapping == child_category and expected_mapping == parent_category:
                return f"Extracted child category '{child_category}' instead of parent category '{parent_category}'"
        
        return f"Expected '{expected_mapping}' but got '{actual_mapping}'"
    
    def _generate_validation_summary(self, validation_results: List[Dict]) -> Dict:
        """
        Generate summary statistics from validation results.
        
        Args:
            validation_results: List of validation results
            
        Returns:
            Summary dictionary
        """
        total = len(validation_results)
        correct = sum(1 for result in validation_results if result['validation']['is_correct'])
        incorrect = total - correct
        
        # Group issues by type
        issues = {}
        for result in validation_results:
            if not result['validation']['is_correct']:
                issue = result['validation']['issue']
                if issue:
                    issues[issue] = issues.get(issue, 0) + 1
        
        return {
            "total_rows": total,
            "correct_mappings": correct,
            "incorrect_mappings": incorrect,
            "accuracy_percentage": round((correct / total) * 100, 2) if total > 0 else 0,
            "common_issues": dict(sorted(issues.items(), key=lambda x: x[1], reverse=True)[:5])
        }
    
    def _save_validation_report(self, validation_report: Dict) -> None:
        """
        Save the validation report to a JSON file.
        
        Args:
            validation_report: The validation report to save
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Category_Mapping_Validation_{timestamp}.json"
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(validation_report, f, indent=2, ensure_ascii=False)
    
    def _get_validation_report_path(self) -> str:
        """
        Get the path of the most recent validation report.
        
        Returns:
            Path to the validation report
        """
        files = [f for f in os.listdir(self.output_dir) if f.startswith("Category_Mapping_Validation_")]
        if not files:
            return "No validation report found"
        
        # Get the most recent file
        latest_file = max(files, key=lambda x: os.path.getctime(os.path.join(self.output_dir, x)))
        return os.path.join(self.output_dir, latest_file)


def validate_category_overhaul_matrix_automation(matrix_data: List[Dict], analysis_timestamp: str = None) -> Dict:
    """
    Automated validation function for Category Overhaul Matrix.
    
    Args:
        matrix_data: The Category Overhaul Matrix data
        analysis_timestamp: Timestamp of the analysis (optional)
        
    Returns:
        Validation results
    """
    validator = CategoryMappingValidator()
    return validator.validate_category_overhaul_matrix(matrix_data, analysis_timestamp)
