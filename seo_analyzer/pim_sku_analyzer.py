"""
PIM SKU Analyzer Module

This module processes PIM/SKU CSV files and matches them to category-facet combinations
from the Category Overhaul Matrix, providing intelligent matching with context awareness.
"""
import pandas as pd
import numpy as np
import re
from typing import Dict, List, Tuple, Optional, Set
from collections import defaultdict
import spacy
import sys
import subprocess
import time
from functools import lru_cache


# Try to load spaCy NLP model for intelligent matching
try:
    nlp = spacy.load("en_core_web_md")
except OSError:
    try:
        subprocess.run([sys.executable, "-m", "spacy", "download", "en_core_web_md"], check=True)
        nlp = spacy.load("en_core_web_md")
    except (subprocess.CalledProcessError, OSError):
        print("Warning: spaCy model not available. Intelligent matching will be limited.")
        nlp = None


def analyze_pim_skus(
    pim_csv_path: str,
    category_facet_map: List[Dict],
    sku_id_column: str = None,
    progress_reporter: callable = None
) -> Dict:
    """
    Analyze PIM CSV file and match SKUs to category-facet combinations.
    
    Args:
        pim_csv_path: Path to the PIM CSV file
        category_facet_map: List of dictionaries with 'Category Mapping' and 'Facet Value' keys
        sku_id_column: Name of the SKU ID column (auto-detected if None)
        
    Returns:
        Dictionary with:
        - 'category_facet_counts': List of dicts with Category Mapping, Facet Value, and SKU Count
        - 'total_skus': Total number of SKUs processed
        - 'matched_skus': Number of SKUs that matched at least one category-facet combination
        - 'match_breakdown': Detailed breakdown of matches per SKU
    """
    try:
        # Load PIM CSV file
        pim_df = pd.read_csv(pim_csv_path)
        
        # Auto-detect SKU ID column if not provided
        if sku_id_column is None:
            sku_id_column = _detect_sku_column(pim_df)
        
        if sku_id_column is None or sku_id_column not in pim_df.columns:
            raise ValueError(f"SKU ID column '{sku_id_column}' not found in PIM CSV")
        
        # Normalize category-facet map
        category_facet_pairs = _normalize_category_facet_map(category_facet_map)
        
        # Extract known values from category-facet map
        known_categories = set()
        known_facet_values = defaultdict(set)  # Maps facet type to set of values
        
        for pair in category_facet_pairs:
            cat = pair.get('Category Mapping', '').strip()
            facet_val = pair.get('Facet Value', '').strip()
            if cat:
                known_categories.add(cat.lower())
            if facet_val:
                # Infer facet type from context (this is a simplified approach)
                facet_type = _infer_facet_type(facet_val)
                known_facet_values[facet_type].add(facet_val.lower())
        
        # Build matching knowledge base
        knowledge_base = _build_knowledge_base(category_facet_pairs, pim_df)
        
        # Get total rows for progress reporting
        total_rows = len(pim_df)
        
        # Report progress: Starting embedding pre-computation
        if progress_reporter:
            progress_reporter("Pre-computing NLP embeddings for category-facet values...", 0, total_rows + 100)
        
        # Pre-compute NLP embeddings for all unique category-facet values (PERFORMANCE OPTIMIZATION)
        # This way we process each unique value only once, not thousands of times
        embedding_cache = None
        column_embeddings_cache = None  # Cache for column name embeddings (facet attribute matching)
        facet_attribute_embeddings_cache = None  # Cache for facet attribute embeddings
        
        if nlp is not None:
            try:
                print("Pre-computing NLP embeddings for category-facet values...")
                embedding_cache = _precompute_embeddings(category_facet_pairs, nlp, progress_reporter)
                print(f"Pre-computed {len(embedding_cache)} embeddings")
                
                # Pre-compute embeddings for all column names (MAJOR PERFORMANCE BOOST)
                # This allows fast semantic matching of facet attributes to column names
                print("Pre-computing NLP embeddings for column names (facet attribute matching)...")
                column_embeddings_cache = {}
                for col in all_columns:
                    try:
                        col_lower = col.lower()
                        col_doc = nlp(col_lower)
                        column_embeddings_cache[col] = {
                            'embedding': col_doc.vector,
                            'keywords': [token.lemma_.lower() for token in col_doc if not token.is_stop and token.is_alpha]
                        }
                    except Exception:
                        continue  # Skip if NLP fails for this column
                print(f"Pre-computed {len(column_embeddings_cache)} column name embeddings")
                
                # Pre-compute embeddings for all unique facet attributes (ADDITIONAL PERFORMANCE BOOST)
                # This avoids processing the same facet attribute thousands of times
                print("Pre-computing NLP embeddings for facet attributes...")
                facet_attribute_embeddings_cache = {}
                unique_facet_attributes = set()
                for pair in category_facet_pairs:
                    facet_attr = pair.get('Facet Attribute', '').strip()
                    if facet_attr and facet_attr not in ['(Blank)', 'Root Category']:
                        unique_facet_attributes.add(facet_attr.lower())
                
                for facet_attr_lower in unique_facet_attributes:
                    try:
                        attr_doc = nlp(facet_attr_lower)
                        facet_attribute_embeddings_cache[facet_attr_lower] = {
                            'embedding': attr_doc.vector,
                            'keywords': [token.lemma_.lower() for token in attr_doc if not token.is_stop and token.is_alpha],
                            'norm': np.linalg.norm(attr_doc.vector)
                        }
                    except Exception:
                        continue  # Skip if NLP fails for this attribute
                print(f"Pre-computed {len(facet_attribute_embeddings_cache)} facet attribute embeddings")
            except Exception as e:
                print(f"Warning: Failed to pre-compute embeddings: {str(e)}. Continuing without embedding cache.")
                import traceback
                traceback.print_exc()
                embedding_cache = None
                column_embeddings_cache = None
                facet_attribute_embeddings_cache = None
        else:
            print("NLP model not available, skipping embedding pre-computation")
        
        # Pre-compute column lists for better performance
        all_columns = pim_df.columns.tolist()
        brand_columns = [col for col in all_columns if any(term in col.lower() for term in ['brand', 'make', 'manufacturer'])]
        category_columns = [col for col in all_columns if any(term in col.lower() for term in ['category', 'type']) and not re.search(r'product.*type', col.lower())]
        
        # Match SKUs to category-facet combinations
        # Add progress reporting for large files
        sku_matches = []
        print(f"Starting PIM analysis: {total_rows} SKUs to process against {len(category_facet_pairs)} category-facet combinations")
        
        # Pre-process SKU text embeddings for faster matching (PERFORMANCE OPTIMIZATION)
        # Process each SKU once and cache its text embeddings - ALL COLUMNS, ALL TEXT
        if progress_reporter:
            progress_reporter("Pre-processing SKU text embeddings (all columns, full text)...", 10, total_rows + 100)
        
        print("Pre-processing SKU text embeddings (all columns, full text)...")
        sku_text_cache = {}
        if nlp is not None:
            for idx, (_, row) in enumerate(pim_df.iterrows()):
                if progress_reporter and idx % 50 == 0:
                    progress_reporter(f"Pre-processing SKU {idx}/{total_rows}...", 10 + idx, total_rows + 100)
                
                try:
                    sku_id = row[sku_id_column]
                    if pd.isna(sku_id) or not str(sku_id).strip():
                        continue
                    
                    # Get ALL text content from ALL columns in the SKU row (no truncation)
                    sku_text = ' '.join([
                        str(val) for val in row.values 
                        if pd.notna(val) and str(val).strip()
                    ]).lower()
                    
                    if sku_text and len(sku_text) > 10:  # Only cache if there's substantial text
                        try:
                            # Process FULL SKU text with NLP (no truncation for accuracy)
                            # This processes all columns and all text within them
                            sku_doc = nlp(sku_text)  # Process full text, no truncation
                            
                            # Store column text for later processing (lazy evaluation)
                            # We'll process individual columns only if needed during matching
                            column_texts = {}
                            for col in all_columns:
                                if col in row.index and pd.notna(row[col]):
                                    cell_value = str(row[col]).strip()
                                    if cell_value and len(cell_value) > 5:  # Only store substantial cells
                                        column_texts[col] = cell_value.lower()
                            
                            sku_text_cache[str(sku_id)] = {
                                'text': sku_text,
                                'embedding': sku_doc.vector,
                                'keywords': [token.lemma_.lower() for token in sku_doc if not token.is_stop and token.is_alpha],
                                'column_texts': column_texts  # Store column texts for lazy processing
                            }
                        except Exception as e:
                            # If NLP fails for this SKU, cache text without embedding
                            sku_text_cache[str(sku_id)] = {
                                'text': sku_text,
                                'embedding': None,
                                'keywords': [],
                                'column_texts': {}
                            }
                except Exception as e:
                    # If processing fails for this SKU, continue
                    continue
        
        print(f"Pre-processed {len(sku_text_cache)} SKU text embeddings")
        
        if progress_reporter:
            progress_reporter("Starting SKU matching...", total_rows + 20, total_rows + 100)
        
        # Now match SKUs to category-facet combinations using cached embeddings
        # Process ALL columns and ALL text within cells for full semantic matching
        print("Matching SKUs to category-facet combinations (processing all columns and full text)...")
        print(f"Total comparisons to make: {total_rows} SKUs × {len(category_facet_pairs)} combinations = {total_rows * len(category_facet_pairs)}")
        print("Processing EVERY column, EVERY row, EVERY character for maximum accuracy...")
        
        # Use itertuples() instead of iterrows() for better performance (3-5x faster)
        # Convert to list of tuples for faster iteration while still accessing all data
        for idx, row_tuple in enumerate(pim_df.itertuples(index=False)):
            # Report progress every 5 SKUs for better feedback during long processing
            # This ensures the user knows the system is working even with maximum accuracy processing
            if progress_reporter and idx % 5 == 0:
                progress_reporter(f"Matching SKU {idx}/{total_rows}... ({len(sku_matches)} matches found, checking all columns)", total_rows + 20 + idx, total_rows + 100)
            elif idx % 25 == 0 and idx > 0:
                print(f"Processing SKU {idx}/{total_rows}... ({len(sku_matches)} matches found, checking all columns and all text)")
            
            # Convert tuple back to Series for compatibility with existing code
            # This is still faster than iterrows() because itertuples() is much faster
            row = pd.Series(row_tuple, index=all_columns)
            
            try:
                sku_id = row[sku_id_column]
                if pd.isna(sku_id) or not str(sku_id).strip():
                    continue
                
                # Get cached SKU text data if available
                sku_text_data = sku_text_cache.get(str(sku_id))
                
                matches = _match_sku_to_category_facets(
                    row, 
                    category_facet_pairs, 
                    knowledge_base,
                    all_columns,  # Process ALL columns
                    brand_columns,
                    category_columns,
                    embedding_cache,  # Pass pre-computed embeddings
                    sku_text_data,  # Pass pre-processed SKU text data (full text from all columns)
                    column_embeddings_cache,  # Pass pre-computed column name embeddings (facet attribute matching)
                    nlp,  # Pass NLP model for semantic matching
                    facet_attribute_embeddings_cache  # Pass pre-computed facet attribute embeddings
                )
                if matches:
                    sku_matches.append({
                        'sku_id': sku_id,
                        'matches': matches
                    })
            except Exception as e:
                # Log error but continue processing other SKUs
                print(f"Error processing SKU {idx}: {str(e)}")
                import traceback
                if idx < 5:  # Only print full traceback for first few errors
                    traceback.print_exc()
                continue
        
        print(f"PIM analysis complete: {len(sku_matches)} SKUs matched out of {total_rows} total")
        
        # Count SKUs per category-facet combination and collect SKU IDs
        category_facet_counts = defaultdict(int)
        category_facet_sku_ids = defaultdict(list)  # Store SKU IDs for each combination
        matched_sku_ids = set()
        
        for sku_match in sku_matches:
            sku_id = sku_match['sku_id']
            # Convert SKU ID to string for consistency
            sku_id_str = str(sku_id).strip() if pd.notna(sku_id) else None
            if not sku_id_str:
                continue
                
            matched_sku_ids.add(sku_id_str)
            for match in sku_match['matches']:
                # Include Facet Attribute in the key for proper matching
                key = (match['category'], match.get('facet_attribute', ''), match['facet_value'])
                category_facet_counts[key] += 1
                # Store SKU ID for this combination (as string)
                if sku_id_str not in category_facet_sku_ids[key]:
                    category_facet_sku_ids[key].append(sku_id_str)
        
        # Format results with SKU IDs
        result_list = []
        for (category, facet_attribute, facet_value), count in category_facet_counts.items():
            sku_ids = category_facet_sku_ids.get((category, facet_attribute, facet_value), [])
            # Ensure all SKU IDs are strings and filter out any empty/invalid values
            sku_ids_clean = [str(sid).strip() for sid in sku_ids if pd.notna(sid) and str(sid).strip() and str(sid).strip().lower() != 'nan']
            # Sort SKU IDs for consistency
            sku_ids_sorted = sorted(set(sku_ids_clean))  # Use set to remove duplicates
            
            result_list.append({
                'Category Mapping': category,
                'Facet Attribute': facet_attribute if facet_attribute else '',
                'Facet Value': facet_value,
                'SKU Count': count,
                'SKU IDs': sku_ids_sorted
            })
        
        # Sort by category, then by facet attribute, then by facet value
        result_list.sort(key=lambda x: (x['Category Mapping'], x.get('Facet Attribute', ''), x['Facet Value']))
        
        return {
            'category_facet_counts': result_list,
            'total_skus': len(pim_df),
            'matched_skus': len(matched_sku_ids),
            'match_breakdown': sku_matches,
            'sku_ids_by_combination': {str(k): v for k, v in category_facet_sku_ids.items()}
        }
        
    except Exception as e:
        raise ValueError(f"Error analyzing PIM SKUs: {str(e)}")


def _detect_sku_column(df: pd.DataFrame) -> Optional[str]:
    """Auto-detect SKU ID column from common naming patterns."""
    sku_patterns = [
        r'sku',
        r'product.*id',
        r'item.*id',
        r'product.*code',
        r'item.*code',
        r'ean',
        r'barcode'
    ]
    
    for col in df.columns:
        col_lower = col.lower().strip()
        for pattern in sku_patterns:
            if re.search(pattern, col_lower):
                return col
    return None


def _normalize_category_facet_map(category_facet_map: List[Dict]) -> List[Dict]:
    """Normalize category-facet map data."""
    normalized = []
    for item in category_facet_map:
        cat = item.get('Category Mapping', '').strip()
        facet_attr = item.get('Facet Attribute', '').strip()
        facet_value = item.get('Facet Value', '').strip()
        if cat or facet_value:
            normalized.append({
                'Category Mapping': cat if cat else '(Blank)',
                'Facet Attribute': facet_attr if facet_attr else '(Blank)',
                'Facet Value': facet_value if facet_value else '(Blank)'
            })
    return normalized


def _infer_facet_type(facet_value: str) -> str:
    """Infer the facet type from the value (simplified)."""
    # This is a basic inference - could be enhanced
    facet_lower = facet_value.lower()
    
    # Brand patterns
    if re.search(r'\b(brand|make|manufacturer)\b', facet_lower):
        return 'brand'
    
    # Color patterns
    if re.search(r'\b(color|colour|paint|finish|finish.*type)\b', facet_lower):
        return 'color'
    
    # Size patterns
    if re.search(r'\b(size|dimension|volume|capacity)\b', facet_lower):
        return 'size'
    
    return 'other'


def _build_knowledge_base(
    category_facet_pairs: List[Dict],
    pim_df: pd.DataFrame
) -> Dict:
    """Build a knowledge base for intelligent matching."""
    knowledge_base = {
        'known_categories': set(),
        'known_facet_values': set(),
        'facet_value_aliases': defaultdict(set),
        'category_patterns': []
    }
    
    for pair in category_facet_pairs:
        cat = pair.get('Category Mapping', '').strip().lower()
        facet = pair.get('Facet Value', '').strip().lower()
        
        if cat and cat != '(blank)':
            knowledge_base['known_categories'].add(cat)
        
        if facet and facet != '(blank)':
            knowledge_base['known_facet_values'].add(facet)
            # Add normalized versions
            normalized = _normalize_value(facet)
            if normalized != facet:
                knowledge_base['facet_value_aliases'][facet].add(normalized)
    
    return knowledge_base


def _normalize_value(value: str) -> str:
    """
    Normalize a value for matching by handling special characters intelligently.
    
    This function normalizes hyphens, underscores, and other separators to spaces,
    ensuring that "Anti-Climb Paint" matches "Anti Climb Paint".
    
    Special characters normalized:
    - Hyphens (-)
    - Underscores (_)
    - Various separators (/, |, \, etc.)
    - Other punctuation that acts as separators
    """
    if not value:
        return ''
    
    # Convert to lowercase first
    normalized = value.lower().strip()
    
    # Replace common separators with spaces
    # Hyphens, underscores, forward/back slashes, pipes, etc.
    normalized = re.sub(r'[-_/\\|]+', ' ', normalized)
    
    # Replace other punctuation that might act as separators (but keep them as spaces)
    # This includes: periods, commas, colons, semicolons when surrounded by word characters
    normalized = re.sub(r'[.,;:]+(?=\s|$)|(?<=\s)[.,;:]+', '', normalized)  # Remove trailing/leading punctuation
    
    # Replace remaining special characters with spaces (but preserve alphanumeric and spaces)
    normalized = re.sub(r'[^\w\s]', ' ', normalized)
    
    # Collapse multiple spaces into single space and trim
    normalized = ' '.join(normalized.split())
    
    return normalized


def _precompute_embeddings(category_facet_pairs: List[Dict], nlp_model, progress_reporter: callable = None) -> Dict[str, any]:
    """
    Pre-compute NLP embeddings for all unique category-facet values.
    This dramatically improves performance by processing each value only once.
    """
    if nlp_model is None:
        return {}
    
    embedding_cache = {}
    unique_values = set()
    
    # Collect all unique category and facet values
    for pair in category_facet_pairs:
        category = pair.get('Category Mapping', '').strip()
        facet_value = pair.get('Facet Value', '').strip()
        
        if category and category != '(Blank)':
            unique_values.add(category.lower())
        if facet_value and facet_value != '(Blank)':
            unique_values.add(facet_value.lower())
    
    # Pre-compute embeddings for all unique values
    print(f"Processing {len(unique_values)} unique values with NLP...")
    processed_count = 0
    total_values = len(unique_values)
    
    for idx, value in enumerate(unique_values):
        try:
            doc = nlp_model(value)
            if doc.vector is not None and len(doc.vector) > 0:
                embedding_cache[value] = doc.vector  # Cache the vector (300-dimensional for en_core_web_md)
                processed_count += 1
            
            # Report progress every 50 values
            if progress_reporter and (idx + 1) % 50 == 0:
                progress_reporter(f"Pre-computing embeddings: {processed_count}/{total_values}...", idx + 1, total_values)
        except Exception as e:
            # If processing fails, continue without caching this value
            print(f"  Warning: Failed to process '{value}': {str(e)}")
            continue
    
    print(f"Successfully cached {len(embedding_cache)} embeddings")
    return embedding_cache


def _match_sku_to_category_facets(
    sku_row: pd.Series,
    category_facet_pairs: List[Dict],
    knowledge_base: Dict,
    all_columns: List[str],
    brand_columns: List[str] = None,
    category_columns: List[str] = None,
    embedding_cache: Dict = None,
    sku_text_data: Dict = None,
    column_embeddings_cache: Dict = None,
    nlp = None,
    facet_attribute_embeddings_cache: Dict = None
) -> List[Dict]:
    """
    Match a single SKU to category-facet combinations with intelligent matching.
    
    This function uses context-aware matching to avoid false positives (e.g., 
    matching "lick" as the brand "Lick" when it appears in other contexts).
    
    Processes ALL columns, ALL rows, and ALL text within cells for maximum accuracy.
    """
    matches = []
    
    # Track processing stats for debugging (not used in production, just for monitoring)
    total_checks = 0
    
    # Get all text content from the SKU row (use cached if available)
    if sku_text_data and 'text' in sku_text_data:
        sku_text = sku_text_data['text']
        sku_embedding_cached = sku_text_data.get('embedding')
        sku_keywords_cached = sku_text_data.get('keywords', [])
    else:
        sku_text = ' '.join([
            str(val) for val in sku_row.values 
            if pd.notna(val) and str(val).strip()
        ]).lower()
        sku_embedding_cached = None
        sku_keywords_cached = None
    
    # Use pre-computed column lists if provided, otherwise compute them
    if brand_columns is None:
        brand_columns = [col for col in all_columns if any(term in col.lower() for term in ['brand', 'make', 'manufacturer'])]
    if category_columns is None:
        category_columns = [col for col in all_columns if any(term in col.lower() for term in ['category', 'type']) and not re.search(r'product.*type', col.lower())]
    
    for pair in category_facet_pairs:
        category = pair.get('Category Mapping', '').strip()
        facet_attribute = pair.get('Facet Attribute', '').strip()
        facet_value = pair.get('Facet Value', '').strip()
        
        if not category and not facet_value:
            continue
        
        # Check if this is a "Root Category" match (category only, no facets)
        is_root_category = (facet_attribute == 'Root Category' or facet_value == 'Root Category')
        
        # Match category
        category_matched = False
        if not category or category == '(Blank)':
            category_matched = True
        else:
            # For categories, search in all columns (not just category_columns)
            # Categories like "Anti Mould Paint" can appear in product names, descriptions, etc.
            category_matched = _intelligent_match(
                category, 
                sku_row, 
                sku_text,
                all_columns,  # Search ALL columns for categories, not just category_columns
                knowledge_base,
                match_type='category',
                embedding_cache=embedding_cache,  # Pass embedding cache
                sku_embedding_cached=sku_embedding_cached,  # Pass cached SKU embedding
                sku_keywords_cached=sku_keywords_cached  # Pass cached SKU keywords
            )
        
        # For Root Category, only category match is needed
        if is_root_category:
            if category_matched:
                matches.append({
                    'category': category if category else '(Blank)',
                    'facet_attribute': 'Root Category',
                    'facet_value': 'Root Category'
                })
            continue  # Skip facet matching for Root Category
        
        # Match facet attribute using PURELY SEMANTIC matching via NLP embeddings
        # No hardcoded patterns or dictionaries - works intelligently for ANY attribute combination
        # Uses NLP to detect semantic similarity: "Colour" matches "Colour_Group", "Brand" matches "Product Brand", etc.
        facet_attribute_matched = False
        relevant_columns_for_facet = all_columns  # Initialize with all columns as fallback
        
        if not facet_attribute or facet_attribute == '(Blank)' or facet_attribute == 'Root Category':
            facet_attribute_matched = True  # If no attribute specified, consider matched
        else:
            facet_attribute_lower = facet_attribute.lower().strip()
            matching_columns = []
            
            # PRIMARY METHOD: Use PURELY SEMANTIC matching via NLP embeddings
            # This intelligently detects matches for ANY attribute type without hardcoded patterns
            # Works for: "Colour" vs "Colour_Group", "Brand" vs "Manufacturer Brand", "Material" vs "Product Material", etc.
            if nlp is not None:
                try:
                    # Use pre-computed facet attribute embedding if available (MAJOR PERFORMANCE BOOST)
                    # This avoids processing the same facet attribute thousands of times
                    if facet_attribute_embeddings_cache and facet_attribute_lower in facet_attribute_embeddings_cache:
                        attr_data = facet_attribute_embeddings_cache[facet_attribute_lower]
                        attr_embedding = attr_data['embedding']
                        attr_keywords = attr_data['keywords']
                        attr_norm = attr_data['norm']
                    else:
                        # Fallback: Process facet attribute with NLP on-demand (slower, but still works)
                        attr_doc = nlp(facet_attribute_lower)
                        attr_embedding = attr_doc.vector
                        attr_keywords = [token.lemma_.lower() for token in attr_doc if not token.is_stop and token.is_alpha]
                        attr_norm = np.linalg.norm(attr_embedding)
                    
                    # Use pre-computed column embeddings if available (MAJOR PERFORMANCE BOOST)
                    # This avoids processing the same column names thousands of times
                    if column_embeddings_cache and attr_norm > 0:
                        # Fast path: Use pre-computed column embeddings
                        for col, col_data in column_embeddings_cache.items():
                            try:
                                col_embedding = col_data['embedding']
                                col_keywords = col_data.get('keywords', [])
                                col_norm = np.linalg.norm(col_embedding)
                                
                                if col_norm > 0:
                                    # Calculate cosine similarity using pre-computed embeddings (VERY FAST)
                                    similarity = np.dot(attr_embedding, col_embedding) / (attr_norm * col_norm)
                                    
                                    # Use intelligent semantic threshold (works for ANY attribute type)
                                    if similarity >= 0.65:  # Semantic threshold for intelligent attribute matching
                                        # Validate with keyword overlap to ensure semantic match is meaningful
                                        if len(attr_keywords) > 0 and len(col_keywords) > 0:
                                            # Check if key words from attribute appear in column keywords
                                            matching_keywords = sum(1 for kw in attr_keywords if kw in col_keywords)
                                            matching_ratio = matching_keywords / len(attr_keywords) if len(attr_keywords) > 0 else 0
                                            
                                            # Require meaningful keyword overlap for validation
                                            if matching_ratio >= 0.3 or (similarity >= 0.80):  # Lower threshold for very high similarity
                                                matching_columns.append(col)
                                        else:
                                            # If no keywords available, rely purely on semantic similarity
                                            if similarity >= 0.80:
                                                matching_columns.append(col)
                            except Exception:
                                continue  # Skip if calculation fails
                    else:
                        # Fallback: Process column names with NLP on-demand (slower, but still works)
                        for col in all_columns:
                            col_lower = col.lower()
                            try:
                                # Process column name with NLP to get semantic embedding
                                col_doc = nlp(col_lower)
                                col_embedding = col_doc.vector
                                col_keywords = [token.lemma_.lower() for token in col_doc if not token.is_stop and token.is_alpha]
                                col_norm = np.linalg.norm(col_embedding)
                                
                                if attr_norm > 0 and col_norm > 0:
                                    similarity = np.dot(attr_embedding, col_embedding) / (attr_norm * col_norm)
                                    
                                    if similarity >= 0.65:
                                        if len(attr_keywords) > 0 and len(col_keywords) > 0:
                                            matching_keywords = sum(1 for kw in attr_keywords if kw in col_keywords)
                                            matching_ratio = matching_keywords / len(attr_keywords) if len(attr_keywords) > 0 else 0
                                            if matching_ratio >= 0.3 or (similarity >= 0.80):
                                                matching_columns.append(col)
                                        else:
                                            if similarity >= 0.80:
                                                matching_columns.append(col)
                            except Exception:
                                continue  # Skip if NLP fails for this column
                except Exception:
                    # If NLP fails entirely, fall back to normalized substring matching (better than missing matches)
                    pass
            
            # FALLBACK: If no semantic matches found (or NLP unavailable), try normalized substring matching
            # This catches exact matches and simple variations (handles underscores, hyphens, spaces)
            if not matching_columns:
                attr_normalized = facet_attribute_lower.replace('_', ' ').replace('-', ' ').replace(' ', '').strip()
                for col in all_columns:
                    col_lower = col.lower()
                    col_normalized = col_lower.replace('_', ' ').replace('-', ' ').replace(' ', '').strip()
                    
                    # Normalized exact/substring match (fallback only)
                    if (attr_normalized == col_normalized or 
                        attr_normalized in col_normalized or 
                        col_normalized in attr_normalized):
                        matching_columns.append(col)
            
            # Use matching columns for facet value matching (prioritizes semantic matches)
            if matching_columns:
                facet_attribute_matched = True
                # Store matching columns for use in facet value matching
                # These columns represent where the facet attribute was found semantically
                relevant_columns_for_facet = matching_columns
            else:
                # If no matching column found, still allow matching (fallback to all columns)
                # This prevents missing matches due to column naming differences
                # But it means the facet value will be searched across all columns (less precise)
                facet_attribute_matched = True
                relevant_columns_for_facet = all_columns
        
        # Match facet value (only if attribute matched or is Root Category)
        facet_value_matched = False
        if not facet_value or facet_value == '(Blank)' or str(facet_value).strip() == '':
            facet_value_matched = True
        elif facet_attribute_matched:
            # Search in relevant columns (those matching the facet attribute) for maximum accuracy
            # This prevents false positives like "stone" (material) matching "Stone" (colour)
            facet_value_matched = _intelligent_match(
                facet_value,
                sku_row,
                sku_text,
                relevant_columns_for_facet,  # Use attribute-matched columns (already initialized)
                knowledge_base,
                match_type='facet',
                embedding_cache=embedding_cache,  # Pass embedding cache
                sku_embedding_cached=sku_embedding_cached,  # Pass cached SKU embedding
                sku_keywords_cached=sku_keywords_cached  # Pass cached SKU keywords
            )
        
        # CRITICAL: BOTH category AND (facet attribute AND facet value) must match for a SKU to be counted
        # Example: A SKU with "Stone" color will ONLY appear in combinations where
        # BOTH the category mapping matches AND "Colour" attribute matches AND "Stone" matches.
        # It will NOT appear in combinations for "Stone" (material) attribute.
        if category_matched and facet_attribute_matched and facet_value_matched:
            matches.append({
                'category': category if category else '(Blank)',
                'facet_attribute': facet_attribute if facet_attribute else '(Blank)',
                'facet_value': facet_value if facet_value else '(Blank)'
            })
    
    return matches


def _intelligent_match(
    target_value: str,
    sku_row: pd.Series,
    sku_text: str,
    relevant_columns: List[str],
    knowledge_base: Dict,
    match_type: str = 'facet',
    embedding_cache: Dict = None,
    sku_embedding_cached: np.ndarray = None,
    sku_keywords_cached: List[str] = None
) -> bool:
    """
    Intelligently match a target value against SKU data using multiple strategies:
    
    1. Exact/substring matching (highest confidence)
    2. Semantic similarity using NLP embeddings (handles variations)
    3. Word boundary matching (prevents false positives)
    
    Examples:
    - "Anti Mould Paint" can match "mould-resistant paint" or "paint that prevents mould"
    - Uses spaCy semantic similarity for context-aware matching
    """
    target_lower = target_value.lower().strip()
    target_normalized = _normalize_value(target_value)
    
    # Quick check: For multi-word phrases, do a simple substring check in full text first
    # This catches obvious matches like "anti mould paint" in product names
    # Use normalized values to handle hyphens and special characters (e.g., "Anti-Climb" matches "Anti Climb")
    target_words = target_lower.split()
    
    # For categories, check even shorter phrases and allow partial matches
    min_length = 6 if match_type == 'category' else 8
    if len(target_words) > 1 and len(target_value.replace(' ', '').replace('-', '').replace('_', '')) >= min_length:
        # Normalize values for comparison (handles hyphens, underscores, special chars)
        target_phrase_simple = _normalize_value(target_lower)
        sku_text_simple = _normalize_value(sku_text)
        
        # Simple substring match - if the phrase appears as-is, it's a match
        # This handles "anti-climb paint" matching "Anti Climb Paint"
        if target_phrase_simple in sku_text_simple:
            # For longer phrases, skip false positive check (they're usually legitimate)
            return True
        
        # For categories, also check if key words appear as substring
        # E.g., "Low VOC Paint" should match "low voc" even if "paint" is missing
        if match_type == 'category' and len(target_words) >= 2:
            # Use normalized target words for checking
            target_words_normalized = _normalize_value(target_lower).split()
            # Check if at least 2 consecutive words appear together
            for i in range(len(target_words_normalized) - 1):
                two_word_phrase = f"{target_words_normalized[i]} {target_words_normalized[i+1]}"
                if two_word_phrase in sku_text_simple:
                    return True
    
    # Strategy 1: Exact match in ALL relevant columns (process every column, every cell, every character)
    # This ensures maximum accuracy by checking every column and every character
    for col in relevant_columns:
        if col not in sku_row.index:
            continue
        
        # Process FULL cell value - every character, no truncation
        cell_value = str(sku_row[col]).strip() if pd.notna(sku_row[col]) else ''
        if not cell_value:
            continue
        
        # Process the ENTIRE cell value - no truncation for maximum accuracy
        
        cell_lower = cell_value.lower()
        cell_normalized = _normalize_value(cell_value)
        
        # Exact match (case-insensitive)
        if target_lower == cell_lower or target_normalized == cell_normalized:
            return True
        
        # Check for exact match within pipe-separated or comma-separated values
        for separator in ['|', ',', ';', '/']:
            values = [v.strip().lower() for v in cell_value.split(separator)]
            if target_lower in values:
                return True
        
        # For multi-word phrases, check if phrase appears in cell value
        target_words = target_lower.split()
        if len(target_words) > 1:
            # For categories, allow partial word matches (e.g., "Low VOC Paint" matches "low voc")
            # This handles cases where the category name includes additional words not in the SKU
            if match_type == 'category':
                # For categories: require at least 2 words or 70% of words to match
                words_found_count = sum(1 for word in target_words if word in cell_lower)
                min_words_required = max(2, int(len(target_words) * 0.7))  # At least 2 words or 70%
                words_found = words_found_count >= min_words_required
            else:
                # For facets: require all words to match (more strict)
                words_found = all(word in cell_lower for word in target_words)
            
            if words_found:
                # Use normalized values for comparison (handles hyphens, underscores, special chars)
                # This ensures "Anti-Climb Paint" matches "Anti Climb Paint"
                target_phrase_normalized = _normalize_value(target_lower)
                cell_normalized = _normalize_value(cell_lower)
                
                # Strategy 1: Full phrase appears as substring (most lenient)
                # This handles "anti mould paint" matching "6 year anti mould paint 2.5l"
                # Also handles "anti-climb paint" matching "Anti Climb Paint"
                if target_phrase_normalized in cell_normalized:
                    return True
                
                # Strategy 2: Remove all spaces and check if phrase matches
                # This handles "antimouldpaint" vs "anti mould paint" variations
                # Also handles "anti-climb-paint" vs "antclimbpaint" etc.
                target_no_spaces = target_phrase_normalized.replace(' ', '')
                cell_no_spaces = cell_normalized.replace(' ', '')
                if target_no_spaces in cell_no_spaces:
                    return True
                
                # Strategy 3: Check if words appear in order and close together
                # Allow words to have other text between them (like "6 year" between words)
                # Use normalized target words to handle hyphens (e.g., "anti-climb" becomes ["anti", "climb"])
                target_words_normalized = target_phrase_normalized.split()
                # Create list of (position, word) tuples using normalized words
                word_positions = [(cell_normalized.find(word), word) for word in target_words_normalized]
                # Filter out -1 (not found)
                word_positions = [(pos, word) for pos, word in word_positions if pos >= 0]
                
                if len(word_positions) >= len(target_words_normalized) if match_type == 'category' else len(word_positions) == len(target_words_normalized):
                    # Sort by position
                    word_positions_sorted = sorted(word_positions, key=lambda x: x[0])
                    sorted_words = [word for pos, word in word_positions_sorted]
                    
                    # Check if words are in correct order and reasonably close (within 100 chars)
                    # For categories, allow partial matches
                    if match_type == 'category':
                        # Check if normalized words appear in order (allow partial matches)
                        target_indices = [target_words_normalized.index(word) for word in sorted_words if word in target_words_normalized]
                        words_in_order = (target_indices == sorted(target_indices)) if target_indices else False
                    else:
                        # For facets, require exact match
                        words_in_order = (sorted_words == target_words_normalized)
                    
                    if words_in_order:
                        first_pos = word_positions_sorted[0][0]
                        last_pos = word_positions_sorted[-1][0] + len(word_positions_sorted[-1][1])
                        if (last_pos - first_pos) < 100:
                            return True
        
        # Word boundary matching (prevents substring matches for single words)
        if _word_boundary_match(target_lower, cell_lower):
            return True
    
    # Strategy 2: Phrase/substring matching for multi-word targets (less strict)
    target_words = target_lower.split()
    if len(target_words) > 1:
        # For categories, allow partial word matches (e.g., "Low VOC Paint" matches "low voc")
        # This handles cases where the category name includes additional words not in the SKU
        if match_type == 'category':
            # For categories: require at least 2 words or 70% of words to match
            words_found_count = sum(1 for word in target_words if word in sku_text)
            min_words_required = max(2, int(len(target_words) * 0.7))  # At least 2 words or 70%
            words_in_text = words_found_count >= min_words_required
        else:
            # For facets: require all words to appear (more strict)
            words_in_text = all(word in sku_text for word in target_words)
        
        if words_in_text:
            # Use normalized values for comparison (handles hyphens, underscores, special chars)
            target_phrase = _normalize_value(target_lower)
            sku_text_normalized = _normalize_value(sku_text)
            
            # Strategy 2a: Check if phrase appears as substring (most reliable)
            # This handles "anti mould paint" in "6 year anti mould paint 2.5l"
            if target_phrase in sku_text_normalized:
                # For multi-word phrases, be less aggressive with false positive checking
                # Only check if it's a very short word or known problematic pattern
                if len(target_phrase.replace(' ', '')) > 8:  # Longer phrases are usually legitimate
                    return True
                elif not _is_likely_false_positive(target_value, sku_text, knowledge_base):
                    return True
            
            # Strategy 2b: Check if words appear in order and reasonably close
            # This handles cases where words might be separated by other text
            # For categories, allow partial word matches (at least 2 words or 70%)
            word_positions = []
            for word in target_words:
                pos = sku_text_normalized.find(word)
                if pos >= 0:
                    word_positions.append((pos, word))
            
            # For categories, require fewer words to match
            min_words_required_for_order = len(target_words) if match_type != 'category' else max(2, int(len(target_words) * 0.7))
            
            if len(word_positions) >= min_words_required_for_order:
                # Check if words appear in order
                positions_sorted = sorted(word_positions, key=lambda x: x[0])
                sorted_words = [word for _, word in positions_sorted]
                
                # For categories, check if words appear in correct relative order (allow partial matches)
                # For facets, require exact order match
                words_in_order = False
                if match_type == 'category':
                    # For categories: check if the words that appear are in the same relative order
                    # E.g., if target is ["low", "voc", "paint"] and SKU has ["low", "voc"], that's valid
                    target_indices = [target_words.index(word) for word in sorted_words if word in target_words]
                    words_in_order = (target_indices == sorted(target_indices)) if target_indices else False
                else:
                    # For facets: require exact order match
                    words_in_order = (sorted_words == target_words)
                
                if words_in_order:
                    # For multi-word phrases, allow more distance between words (up to 100 chars)
                    first_pos = positions_sorted[0][0]
                    last_pos = positions_sorted[-1][0] + len(positions_sorted[-1][1])
                    if (last_pos - first_pos) < 100:
                        if len(target_phrase.replace(' ', '')) > 8:
                            return True
                        elif not _is_likely_false_positive(target_value, sku_text, knowledge_base):
                            return True
    
    # Strategy 3: Word boundary matching in full text
    if _word_boundary_match(target_lower, sku_text):
        # Additional context check for common false positives
        if _is_likely_false_positive(target_value, sku_text, knowledge_base):
            return False
        return True
    
    # Strategy 4: Semantic similarity using NLP (handles semantic variations)
    # This allows "Anti Mould Paint" to match "mould-resistant paint" or "Low VOC Paint" to match "low voc"
    # For categories, use semantic matching more aggressively (even for shorter phrases)
    # Uses pre-computed embeddings for performance
    min_phrase_length = 6 if match_type == 'category' else 8  # More lenient for categories
    use_semantic = nlp is not None and embedding_cache is not None and (
        len(target_words) > 1 or  # Multi-word phrases
        (match_type == 'category' and len(target_value.replace(' ', '')) >= min_phrase_length)  # Categories: be more aggressive
    )
    
    if use_semantic:
        try:
            # Get pre-computed embedding for target (if available) or compute once
            target_embedding = None
            target_keywords = []
            
            if embedding_cache and target_lower in embedding_cache:
                target_embedding = embedding_cache[target_lower]
                # Still need to extract keywords, so process with NLP
                try:
                    target_doc = nlp(target_lower)
                    target_keywords = [token.lemma_.lower() for token in target_doc if not token.is_stop and token.is_alpha]
                except Exception:
                    # If NLP fails, skip this strategy
                    target_embedding = None
            else:
                # If not in cache, compute embedding and keywords once
                try:
                    target_doc = nlp(target_lower)
                    target_embedding = target_doc.vector
                    target_keywords = [token.lemma_.lower() for token in target_doc if not token.is_stop and token.is_alpha]
                except Exception:
                    # If NLP fails, skip this strategy
                    target_embedding = None
            
            # If we couldn't get an embedding, skip this strategy
            if target_embedding is None or len(target_embedding) == 0:
                pass  # Continue to next strategy - NLP processing failed
            else:
                # PERFORMANCE OPTIMIZATION: Prioritize full SKU text comparison using cached embedding
                # This is much faster than processing individual columns
                if sku_embedding_cached is not None and len(sku_embedding_cached) > 0:
                    try:
                        # Use pre-computed SKU embedding (FAST - no NLP processing needed!)
                        # This embedding includes ALL columns and ALL text within them
                        sku_embedding = sku_embedding_cached
                        sku_keywords = sku_keywords_cached if sku_keywords_cached else []
                        
                        # Calculate cosine similarity using cached vectors (VERY FAST)
                        try:
                            target_norm = np.linalg.norm(target_embedding)
                            sku_norm = np.linalg.norm(sku_embedding)
                            if target_norm > 0 and sku_norm > 0:
                                similarity = np.dot(target_embedding, sku_embedding) / (target_norm * sku_norm)
                            else:
                                similarity = 0.0
                        except Exception:
                            similarity = 0.0
                        
                        # Use lower threshold for categories (more lenient matching)
                        similarity_threshold = 0.60 if match_type == 'category' else 0.65
                        keyword_overlap_threshold = 0.5 if match_type == 'category' else 0.6  # More lenient for categories
                        
                        if similarity >= similarity_threshold:
                            # For full text, require key word overlap for validation
                            # For categories, be more lenient - allow partial matches like "low voc" matching "Low VOC Paint"
                            if len(target_keywords) > 0 and sku_keywords:
                                matching_keywords = sum(1 for kw in target_keywords if kw in ' '.join(sku_keywords))
                                # For categories, check if at least half the keywords match
                                # This allows "low voc" (2 keywords) to match "Low VOC Paint" (3 keywords: low, voc, paint)
                                if matching_keywords >= len(target_keywords) * keyword_overlap_threshold:
                                    # Semantic match confirmed - return immediately
                                    return True
                            elif match_type == 'category' and similarity >= 0.70:
                                # For categories with very high similarity, allow match even without keyword overlap
                                # This handles cases where semantic meaning is clear (e.g., "low voc" = "low voc paint")
                                return True
                    except Exception:
                        pass
                
                # Also check individual columns for semantic matching (ALL columns, ALL text)
                # Process EVERY column to ensure maximum accuracy - no prioritization
                # Process ALL columns in relevant_columns (no prioritization - check everything equally)
                # This ensures every column and every character is reviewed for maximum accuracy
                for col in relevant_columns:
                    # Get cell value from row
                    # Process FULL cell value - every character, no truncation
                    if col in sku_row.index and pd.notna(sku_row[col]):
                        cell_value = str(sku_row[col]).strip()
                        if not cell_value:  # Allow processing of shorter cells too (remove minimum length requirement)
                            continue
                        cell_lower = cell_value.lower()
                    else:
                        continue
                    
                    # Process FULL cell text with NLP (every character, no truncation)
                    # This ensures maximum accuracy by processing every character in every cell
                    try:
                        cell_doc = nlp(cell_lower)  # Process FULL text - all characters, all columns
                        cell_embedding = cell_doc.vector
                        
                        # Calculate cosine similarity
                        try:
                            target_norm = np.linalg.norm(target_embedding)
                            cell_norm = np.linalg.norm(cell_embedding)
                            if target_norm > 0 and cell_norm > 0:
                                similarity = np.dot(target_embedding, cell_embedding) / (target_norm * cell_norm)
                            else:
                                similarity = 0.0
                        except Exception:
                            continue
                        
                        # Use lower threshold for categories (more lenient matching)
                        similarity_threshold = 0.60 if match_type == 'category' else 0.65
                        keyword_overlap_threshold = 0.4 if match_type == 'category' else 0.5  # More lenient for categories
                        
                        if similarity >= similarity_threshold:
                            # Quick keyword validation
                            cell_keywords = [token.lemma_.lower() for token in cell_doc if not token.is_stop and token.is_alpha]
                            if len(target_keywords) > 0:
                                matching_keywords = sum(1 for kw in target_keywords if kw in ' '.join(cell_keywords))
                                # For categories, be more lenient - allow partial matches
                                # This allows "low voc" to match "Low VOC Paint" even if "paint" keyword is missing
                                if matching_keywords >= len(target_keywords) * keyword_overlap_threshold:
                                    return True
                            elif match_type == 'category' and similarity >= 0.70:
                                # For categories with very high similarity, allow match even without keyword overlap
                                # This handles cases where semantic meaning is clear
                                return True
                    except Exception:
                        # If NLP fails for this cell, continue to next column
                        continue
        except Exception as e:
            # If NLP processing fails (out of memory, timeout, etc.), continue with other strategies
            # Log the error for debugging (but only once per type)
            if 'nlp_error_logged' not in locals():
                print(f"Warning: NLP semantic matching failed: {str(e)}. Using fallback strategies.")
            pass
    
    # Strategy 5: Normalized matching (handles variations)
    # This should catch cases where special characters differ
    sku_text_normalized = _normalize_value(sku_text)
    if target_normalized in sku_text_normalized:
        # For multi-word phrases longer than 8 characters, skip false positive check
        # (they're usually legitimate matches)
        if len(target_normalized.replace(' ', '')) > 8:
            return True
        # Additional context check for shorter targets
        if _is_likely_false_positive(target_value, sku_text, knowledge_base):
            return False
        return True
    
    # Strategy 6: For multi-word phrases, check if normalized phrase appears as substring
    # This handles variations in spacing/special characters
    if len(target_words) > 1:
        target_normalized_phrase = ' '.join([_normalize_value(word) for word in target_words])
        if target_normalized_phrase in sku_text_normalized:
            # Multi-word phrases are usually legitimate matches
            if len(target_normalized_phrase.replace(' ', '')) > 8:
                return True
            if not _is_likely_false_positive(target_value, sku_text, knowledge_base):
                return True
    
    return False


def _word_boundary_match(target: str, text: str) -> bool:
    """Match target with word boundaries to avoid substring matches."""
    if not target or not text:
        return False
    
    target_lower = target.lower().strip()
    text_lower = text.lower()
    
    # For multi-word phrases, try both word boundary matching and phrase matching
    if ' ' in target_lower or '-' in target_lower:
        # Multi-word phrase: try exact phrase match first (more lenient)
        # Replace spaces/hyphens with flexible whitespace pattern
        phrase_pattern = re.escape(target_lower).replace(r'\ ', r'[\s\-]+').replace(r'\-', r'[\s\-]+')
        if re.search(phrase_pattern, text_lower):
            return True
        
        # Also try word boundary match for the entire phrase
        phrase_escaped = re.escape(target_lower)
        phrase_boundary = r'\b' + phrase_escaped + r'\b'
        if re.search(phrase_boundary, text_lower):
            return True
    
    # Single word or fallback: use word boundary matching
    target_escaped = re.escape(target_lower)
    pattern = r'\b' + target_escaped + r'\b'
    
    return bool(re.search(pattern, text_lower, re.IGNORECASE))


def _is_likely_false_positive(
    target_value: str,
    sku_text: str,
    knowledge_base: Dict
) -> bool:
    """
    Check if a match is likely a false positive.
    
    Examples:
    - "lick" appearing in "click" or "paint that won't lick off" should not match brand "Lick"
    - "low" appearing in "slow" should not match category "Low"
    """
    target_lower = target_value.lower().strip()
    
    # If target is a very short word (3 characters or less), be more cautious
    if len(target_lower) <= 3:
        # Check if it appears as part of a longer word
        words_in_text = set(re.findall(r'\b\w+\b', sku_text.lower()))
        
        # If target is part of many other words, it's likely a false positive
        words_containing_target = [w for w in words_in_text if target_lower in w and w != target_lower]
        
        # If target appears as standalone AND as part of other words, 
        # we need to verify it's not just a substring
        if words_containing_target:
            # Use NLP if available to check context
            if nlp is not None:
                try:
                    doc = nlp(sku_text)
                    # Check if target appears as a named entity or proper noun
                    target_tokens = [token for token in doc if token.text.lower() == target_lower]
                    if not target_tokens:
                        # Target doesn't appear as a standalone token
                        return True
                except Exception:
                    pass
            
            # Conservative approach: if target is very short and appears in many other words,
            # require it to appear as a standalone word with high confidence
            standalone_matches = len([w for w in words_in_text if w == target_lower])
            if standalone_matches == 0 and len(words_containing_target) > 2:
                return True
    
    # Check for common false positive patterns
    false_positive_patterns = [
        (r'\blick\b', r'click|paint.*lick|lick.*off|lick.*surface'),  # "lick" vs "click"
        (r'\blow\b', r'slow|below|allow|follow|hollow'),  # "low" vs "slow"
    ]
    
    for target_pattern, false_positive_pattern in false_positive_patterns:
        if re.search(target_pattern, target_lower):
            if re.search(false_positive_pattern, sku_text, re.IGNORECASE):
                # Check if the false positive pattern matches but target doesn't appear standalone
                if not re.search(r'\b' + re.escape(target_lower) + r'\b', sku_text, re.IGNORECASE):
                    return True
    
    return False

