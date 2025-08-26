import sqlite3
import os
import re
from typing import List, Dict, Tuple, Optional
from urllib.parse import urlparse, parse_qs
from nltk.stem import PorterStemmer
try:
    from .url_parser import URLParser
except ImportError:
    from url_parser import URLParser


class SynonymDiscovery:
    """System for discovering potential synonym rules from new datasets."""
    
    def __init__(self, db_path: str = None):
        """Initialize the discovery system with database."""
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), 'suggestions.db')
        
        self.db_path = db_path
        self.url_parser = URLParser()
        self.stemmer = PorterStemmer()
        self._init_database()
    
    def _init_database(self):
        """Initialize the SQLite database for storing suggestions."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                new_term TEXT NOT NULL,
                suggested_mapping TEXT NOT NULL,
                confidence_score REAL NOT NULL,
                status TEXT DEFAULT 'pending_review',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def discover_synonyms_from_urls(self, urls: List[str]) -> List[Dict]:
        """
        Discover potential synonyms from a list of URLs.
        
        Args:
            urls: List of URLs to analyze
            
        Returns:
            List of discovered synonym candidates
        """
        candidates = []
        
        # Extract all raw facet and category keys
        raw_facet_keys = set()
        raw_category_keys = set()
        
        for url in urls:
            try:
                # Extract category from URL path
                category = self.url_parser.extract_category_from_url(url)
                if category:
                    raw_category_keys.add(category)
                
                # Extract facets from query parameters
                parsed_url = urlparse(str(url))
                query_params = parse_qs(parsed_url.query)
                for key in query_params.keys():
                    raw_facet_keys.add(key)
                    
            except Exception:
                continue
        
        # Find potential synonyms for facet keys
        facet_candidates = self._find_facet_synonyms(raw_facet_keys)
        candidates.extend(facet_candidates)
        
        # Find potential synonyms for category keys
        category_candidates = self._find_category_synonyms(raw_category_keys)
        candidates.extend(category_candidates)
        
        return candidates
    
    def _find_facet_synonyms(self, raw_facet_keys: set) -> List[Dict]:
        """Find potential facet synonyms using Levenshtein distance."""
        candidates = []
        existing_facet_synonyms = self.url_parser.config.get("facet_synonyms", {})
        canonical_keys = set(existing_facet_synonyms.values())
        
        for raw_key in raw_facet_keys:
            if raw_key in existing_facet_synonyms:
                continue
                
            # Find best match using Levenshtein distance
            best_match, confidence = self._find_best_match(raw_key, canonical_keys)
            
            if best_match and confidence > 0.7:  # Threshold for confidence
                candidates.append({
                    'new_term': raw_key,
                    'suggested_mapping': best_match,
                    'confidence_score': confidence,
                    'type': 'facet'
                })
        
        return candidates
    
    def _find_category_synonyms(self, raw_category_keys: set) -> List[Dict]:
        """Find potential category synonyms using Levenshtein distance."""
        candidates = []
        existing_category_synonyms = self.url_parser.config.get("category_synonyms", {})
        canonical_keys = set(existing_category_synonyms.values())
        
        for raw_key in raw_category_keys:
            if raw_key in existing_category_synonyms:
                continue
                
            # Find best match using Levenshtein distance
            best_match, confidence = self._find_best_match(raw_key, canonical_keys)
            
            if best_match and confidence > 0.7:  # Threshold for confidence
                candidates.append({
                    'new_term': raw_key,
                    'suggested_mapping': best_match,
                    'confidence_score': confidence,
                    'type': 'category'
                })
        
        return candidates
    
    def _find_best_match(self, term: str, canonical_terms: set) -> Tuple[Optional[str], float]:
        """Find the best matching canonical term using Levenshtein distance."""
        if not canonical_terms:
            return None, 0.0
        
        best_match = None
        best_confidence = 0.0
        
        for canonical in canonical_terms:
            confidence = self._calculate_similarity(term, canonical)
            if confidence > best_confidence:
                best_confidence = confidence
                best_match = canonical
        
        return best_match, best_confidence
    
    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate similarity between two strings using Levenshtein distance."""
        # Simple Levenshtein distance implementation
        len1, len2 = len(str1), len(str2)
        
        if len1 == 0:
            return 1.0 if len2 == 0 else 0.0
        if len2 == 0:
            return 0.0
        
        # Create matrix
        matrix = [[0] * (len2 + 1) for _ in range(len1 + 1)]
        
        # Initialize first row and column
        for i in range(len1 + 1):
            matrix[i][0] = i
        for j in range(len2 + 1):
            matrix[0][j] = j
        
        # Fill matrix
        for i in range(1, len1 + 1):
            for j in range(1, len2 + 1):
                if str1[i-1] == str2[j-1]:
                    matrix[i][j] = matrix[i-1][j-1]
                else:
                    matrix[i][j] = min(
                        matrix[i-1][j] + 1,    # deletion
                        matrix[i][j-1] + 1,    # insertion
                        matrix[i-1][j-1] + 1   # substitution
                    )
        
        # Calculate similarity
        max_len = max(len1, len2)
        distance = matrix[len1][len2]
        similarity = 1.0 - (distance / max_len)
        
        return similarity
    
    def store_candidates(self, candidates: List[Dict]) -> List[int]:
        """Store discovered candidates in the database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        stored_ids = []
        for candidate in candidates:
            cursor.execute('''
                INSERT INTO suggestions (new_term, suggested_mapping, confidence_score, status)
                VALUES (?, ?, ?, 'pending_review')
            ''', (candidate['new_term'], candidate['suggested_mapping'], candidate['confidence_score']))
            
            stored_ids.append(cursor.lastrowid)
        
        conn.commit()
        conn.close()
        
        return stored_ids
    
    def get_pending_suggestions(self) -> List[Dict]:
        """Get all suggestions with pending_review status."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, new_term, suggested_mapping, confidence_score, created_at
            FROM suggestions
            WHERE status = 'pending_review'
            ORDER BY confidence_score DESC, created_at ASC
        ''')
        
        suggestions = []
        for row in cursor.fetchall():
            suggestions.append({
                'id': row[0],
                'new_term': row[1],
                'suggested_mapping': row[2],
                'confidence_score': row[3],
                'created_at': row[4]
            })
        
        conn.close()
        return suggestions
    
    def update_suggestion_status(self, suggestion_id: int, action: str) -> bool:
        """
        Update the status of a suggestion (approve or reject).
        
        Args:
            suggestion_id: The ID of the suggestion to update
            action: Either 'approve' or 'reject'
            
        Returns:
            True if successful, False otherwise
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            if action == 'approve':
                # Get the suggestion details
                cursor.execute('''
                    SELECT new_term, suggested_mapping
                    FROM suggestions
                    WHERE id = ?
                ''', (suggestion_id,))
                
                row = cursor.fetchone()
                if row:
                    new_term, suggested_mapping = row
                    
                    # Add to configuration
                    self.url_parser.add_facet_synonym(new_term, suggested_mapping)
                    
                    # Update status
                    cursor.execute('''
                        UPDATE suggestions
                        SET status = 'approved'
                        WHERE id = ?
                    ''', (suggestion_id,))
                    
                    conn.commit()
                    conn.close()
                    return True
            
            elif action == 'reject':
                cursor.execute('''
                    UPDATE suggestions
                    SET status = 'rejected'
                    WHERE id = ?
                ''', (suggestion_id,))
                
                conn.commit()
                conn.close()
                return True
            
            return False
            
        except Exception:
            conn.rollback()
            conn.close()
            return False
    
    def bulk_update_suggestions(self, updates: List[Dict]) -> Dict[str, int]:
        """
        Bulk update multiple suggestions.
        
        Args:
            updates: List of dicts with 'id' and 'action' keys
            
        Returns:
            Dict with counts of successful and failed updates
        """
        success_count = 0
        failure_count = 0
        
        for update in updates:
            if self.update_suggestion_status(update['id'], update['action']):
                success_count += 1
            else:
                failure_count += 1
        
        return {
            'success_count': success_count,
            'failure_count': failure_count
        }
