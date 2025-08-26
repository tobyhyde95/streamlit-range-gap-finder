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
                "identifier_patterns": ["^\\d+$", "^cat\\d+$", "^p-\\d+$", "^c\\d+$"],
                "category_synonyms": {},
                "facet_synonyms": {}
            }
    
    def extract_category_from_url(self, url: str) -> Optional[str]:
        """
        Extract category from URL path using intelligent pattern recognition.
        Prioritizes human-readable category names and extracts context from surrounding URL segments.
        
        Args:
            url: The URL to parse
            
        Returns:
            The extracted category or None if not found
        """
        try:
            # Parse URL and get path segments
            parsed_url = urlparse(str(url))
            path_segments = [s for s in parsed_url.path.strip('/').split('/') if s]
            
            # First, look for human-readable category names (non-ID segments)
            human_readable_categories = []
            for segment in path_segments:
                # Skip segments that match identifier patterns
                if self._matches_identifier_pattern(segment):
                    continue
                
                # Clean and process the segment
                cleaned = segment.replace('-', ' ').replace('_', ' ').lower().strip()
                if len(cleaned) > 2 and re.search(r'[a-zA-Z]', cleaned):
                    # Apply stemming and synonym lookup
                    processed = self._post_process_category(cleaned)
                    if processed and processed != cleaned:
                        human_readable_categories.append(processed)
                    else:
                        human_readable_categories.append(cleaned.title())
            
            # If we found human-readable categories, return the most relevant one
            if human_readable_categories:
                # Prefer longer, more descriptive category names
                best_category = max(human_readable_categories, key=len)
                return best_category
            
            # If no human-readable categories found, try to extract context from category IDs
            for segment in reversed(path_segments):
                if self._matches_identifier_pattern(segment):
                    # Try to extract meaningful category name from URL context
                    contextual_name = self._extract_contextual_category_name(segment, path_segments)
                    if contextual_name:
                        return contextual_name
                    # If no contextual name found, skip this ID and continue looking
                    continue
            
            return None
        except Exception:
            return None
    
    def _extract_contextual_category_name(self, category_id: str, path_segments: List[str]) -> Optional[str]:
        """
        Extract a meaningful category name from the URL context around a category ID.
        
        Args:
            category_id: The category ID found in the URL
            path_segments: All path segments from the URL
            
        Returns:
            A meaningful category name or None if no context found
        """
        try:
            # Find the position of the category ID in the path
            id_index = path_segments.index(category_id)
            
            # Look for descriptive segments before the category ID
            contextual_segments = []
            
            # Check segments before the ID (up to 2 segments back)
            for i in range(max(0, id_index - 2), id_index):
                segment = path_segments[i]
                if not self._matches_identifier_pattern(segment):
                    cleaned = segment.replace('-', ' ').replace('_', ' ').title()
                    if len(cleaned) > 2:
                        contextual_segments.append(cleaned)
            
            # Check segments after the ID (up to 1 segment forward)
            for i in range(id_index + 1, min(len(path_segments), id_index + 2)):
                segment = path_segments[i]
                if not self._matches_identifier_pattern(segment):
                    cleaned = segment.replace('-', ' ').replace('_', ' ').title()
                    if len(cleaned) > 2:
                        contextual_segments.append(cleaned)
            
            # If we found contextual segments, combine them intelligently
            if contextual_segments:
                # Remove duplicates while preserving order
                unique_segments = []
                for segment in contextual_segments:
                    if segment not in unique_segments:
                        unique_segments.append(segment)
                
                # Combine segments, preferring the most descriptive
                if len(unique_segments) == 1:
                    return unique_segments[0]
                elif len(unique_segments) >= 2:
                    # Combine the two most relevant segments
                    combined = f"{unique_segments[0]} {unique_segments[1]}"
                    return combined
            
            # If no contextual segments found, try to infer from the category ID pattern
            return self._infer_category_from_id_pattern(category_id)
            
        except (ValueError, IndexError):
            return None
    
    def _infer_category_from_id_pattern(self, category_id: str) -> Optional[str]:
        """
        Infer a category name from the category ID pattern itself.
        
        Args:
            category_id: The category ID to analyze
            
        Returns:
            An inferred category name or None
        """
        # Common patterns in category IDs
        if category_id.startswith('c') and category_id[1:].isdigit():
            # Pattern like c74, c852, etc.
            # Try to extract meaningful information from the number
            number = int(category_id[1:])
            
            # For very low numbers, they might be top-level categories
            if number < 100:
                return "Main Category"
            elif number < 1000:
                return "Sub Category"
            else:
                return "Product Category"
        
        elif category_id.startswith('cat') and category_id[3:].isdigit():
            # Pattern like cat830704
            return "Product Category"
        
        elif category_id.startswith('p-') and category_id[2:].isdigit():
            # Pattern like p-12345
            return "Product Category"
        
        elif category_id.isdigit():
            # Pure numeric ID
            number = int(category_id)
            if number < 100:
                return "Main Category"
            elif number < 1000:
                return "Sub Category"
            else:
                return "Product Category"
        
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
        
        # Strip out file extensions
        cleaned = re.sub(r'\.(html|htm|php|asp|aspx|jsp|jspx|do|action|cfm|shtml|shtm)$', '', cleaned, flags=re.IGNORECASE)
        
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

    def add_category_id_mapping(self, category_id: str, category_name: str) -> None:
        """Add a new category ID mapping to the configuration."""
        if "category_id_mappings" not in self.config:
            self.config["category_id_mappings"] = {}
        self.config["category_id_mappings"][category_id] = category_name
        self.update_config(self.config)
