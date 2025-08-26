import re
import json
import os
from urllib.parse import urlparse, unquote
from nltk.stem import PorterStemmer
from typing import List, Dict, Optional


class URLParser:
    """Enhanced URL parser with configurable normalization rules."""
    
    def __init__(self, config_path: str = None):
        """Initialize the parser with configuration."""
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        
        self.config = self._load_config(config_path)
        self.stemmer = PorterStemmer()
    
    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from JSON file."""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            # Return default config if file doesn't exist
            return {
                "identifier_patterns": ["^\\d+$", "^cat\\d+$", "^p-\\d+$"],
                "category_synonyms": {},
                "facet_synonyms": {}
            }
    
    def extract_category_from_url(self, url: str) -> Optional[str]:
        """
        Extract category from URL path using configurable identifier patterns.
        
        Args:
            url: The URL to parse
            
        Returns:
            The extracted category or None if not found
        """
        try:
            # Parse URL and get path segments
            parsed_url = urlparse(str(url))
            path_segments = [s for s in parsed_url.path.strip('/').split('/') if s]
            
            # Iterate through segments in reverse order
            for segment in reversed(path_segments):
                # Check if segment matches any identifier pattern
                if not self._matches_identifier_pattern(segment):
                    # Apply post-processing to the raw segment
                    return self._post_process_category(segment)
            
            return None
        except Exception:
            return None
    
    def _matches_identifier_pattern(self, segment: str) -> bool:
        """Check if a segment matches any identifier pattern."""
        for pattern in self.config.get("identifier_patterns", []):
            if re.match(pattern, segment, re.IGNORECASE):
                return True
        return False
    
    def _post_process_category(self, raw_segment: str) -> str:
        """
        Apply stemming and synonym lookup to a raw category segment.
        
        Args:
            raw_segment: The raw segment from the URL
            
        Returns:
            The processed category
        """
        # Clean the segment
        cleaned = raw_segment.replace('-', ' ').replace('_', ' ').lower().strip()
        
        # Apply stemming
        stemmed = self.stemmer.stem(cleaned)
        
        # Look up in synonym dictionary
        category_synonyms = self.config.get("category_synonyms", {})
        if stemmed in category_synonyms:
            return category_synonyms[stemmed]
        
        # Return the original cleaned segment if no synonym found
        return cleaned.replace(' ', '-')
    
    def normalize_facet_key(self, raw_facet_key: str) -> str:
        """
        Normalize facet keys using URL decoding and synonym lookup.
        
        Args:
            raw_facet_key: The raw facet key to normalize
            
        Returns:
            The normalized facet key
        """
        # Step 1: Apply URL decoding
        decoded = unquote(raw_facet_key)
        
        # Step 2: Apply existing lowercase and space/hyphen replacement logic
        processed = decoded.lower().replace(' ', '_').replace('-', '_')
        processed = re.sub(r'[^\w_]', '', processed)
        
        # Step 3: Perform synonym lookup
        facet_synonyms = self.config.get("facet_synonyms", {})
        if processed in facet_synonyms:
            return facet_synonyms[processed]
        
        # Return the processed string if no mapping exists
        return processed
    
    def update_config(self, new_config: Dict) -> None:
        """Update the configuration and save to file."""
        self.config.update(new_config)
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        with open(config_path, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def add_category_synonym(self, raw_term: str, canonical_term: str) -> None:
        """Add a new category synonym to the configuration."""
        if "category_synonyms" not in self.config:
            self.config["category_synonyms"] = {}
        self.config["category_synonyms"][raw_term] = canonical_term
        self.update_config(self.config)
    
    def add_facet_synonym(self, raw_term: str, canonical_term: str) -> None:
        """Add a new facet synonym to the configuration."""
        if "facet_synonyms" not in self.config:
            self.config["facet_synonyms"] = {}
        self.config["facet_synonyms"][raw_term] = canonical_term
        self.update_config(self.config)
