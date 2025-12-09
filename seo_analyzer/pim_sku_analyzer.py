"""
PIM SKU Analyzer Module

This module processes PIM/SKU CSV files and matches them to category-facet combinations
from the Category Overhaul Matrix, providing intelligent matching with context awareness.
"""
import pandas as pd
import numpy as np
import re
import math
import html
import os
from typing import Dict, List, Tuple, Optional, Set
from collections import defaultdict
import spacy
from spacy.tokenizer import Tokenizer
from spacy.util import compile_infix_regex
import sys
import subprocess
import time
from functools import lru_cache

try:
    import chardet
except ImportError:
    chardet = None

PROTECTED_PREFIXES = [
    'anti', 'non', 'multi', 'low', 'high', 'quick', 'fast', 'self',
    'water', 'solvent', 'heavy', 'light', 'fire'
]

VERBOSE_CATEGORY_DEBUG = bool(int(os.getenv("SKU_ANALYZER_DEBUG", "0")))
DEBUG_CATEGORY_KEYWORD = os.getenv("SKU_ANALYZER_DEBUG_KEYWORD", "climb").strip().lower()

PREFIX_FUSION_REGEX = re.compile(
    r'\b(' + '|'.join(PROTECTED_PREFIXES) + r')[-\s]+([a-z0-9]+)',
    re.IGNORECASE
)

NEGATIVE_LOOKBEHIND_PATTERN = (
    r'(?<!\bnot\s)'
    r'(?<!\bno\s)'
    r'(?<!\bnon-)'
    r'(?<!\bnon\s)'
    r'(?<!\bexcept\s)'
    r'(?<!\bunlike\s)'
    r'(?<!\bexclude\s)'
)

NEGATIVE_WINDOW_TERMS = ('not', 'no', 'non', 'except', 'unlike', 'exclude')

# ============================================================================
# SMART SKU COUNTING - Column Weighting & Noise Detection (v2.0)
# ============================================================================

# Threshold constants for classification logic
SKU_THRESHOLD_HIGH = 40
TRAFFIC_THRESHOLD_HIGH = 1000

# Column weight configuration for Smart SKU Counting
COLUMN_WEIGHTS = {
    'high_confidence': 10,    # Part Name, Part Name Type
    'medium_confidence': 5,    # Product Brand Name, dynamic/unknown columns
    'low_confidence': 1,       # Description/Copy columns
    'ignore': 0                # TS Product Code
}

# High confidence column patterns
HIGH_CONFIDENCE_COLUMNS = [
    'part name', 'part_name', 'partname',
    'part name type', 'part_name_type', 'partnametype',
    'product name', 'product_name', 'productname'
]

# Low confidence column patterns (description/copy columns)
LOW_CONFIDENCE_COLUMNS = [
    'toolstation web copy', 'web copy', 'webcopy',
    'toolstation catalogue copy', 'catalogue copy', 'cataloguecopy',
    'supplier copy', 'suppliercopy',
    'description', 'desc', 'long description', 'short description',
    'product description', 'product_description'
]

# Columns to ignore completely
IGNORE_COLUMNS = [
    'ts product code', 'product code', 'productcode',
    'sku', 'sku_id', 'id', 'code'
]

# Noise detection threshold (15%)
NOISE_FREQUENCY_THRESHOLD = 0.15


def _get_column_weight(column_name: str) -> int:
    """
    Determine the weight for a column based on its name.
    
    Returns:
        int: Weight value (10, 5, 1, or 0)
    """
    col_lower = column_name.lower().strip()
    
    # Check if column should be ignored
    if any(pattern in col_lower for pattern in IGNORE_COLUMNS):
        return COLUMN_WEIGHTS['ignore']
    
    # Check if column is high confidence
    if any(pattern in col_lower for pattern in HIGH_CONFIDENCE_COLUMNS):
        return COLUMN_WEIGHTS['high_confidence']
    
    # Check if column is low confidence (description/copy)
    if any(pattern in col_lower for pattern in LOW_CONFIDENCE_COLUMNS):
        return COLUMN_WEIGHTS['low_confidence']
    
    # Default: medium confidence for unknown/dynamic columns
    return COLUMN_WEIGHTS['medium_confidence']


def _is_term_noisy(pim_df: pd.DataFrame, term: str, description_columns: List[str], description_corpus: pd.Series = None) -> bool:
    """
    Determine if a search term is "noisy" by checking its frequency in description columns.
    
    PERFORMANCE OPTIMIZED: Uses pre-computed description corpus to avoid row iteration.
    
    Args:
        pim_df: DataFrame containing PIM data
        term: Search term to check
        description_columns: List of description column names
        description_corpus: Pre-computed series of concatenated description text (optional, for performance)
    
    Returns:
        bool: True if term appears in > 15% of rows (noisy), False otherwise (specific)
    """
    if pim_df.empty:
        return False
    
    term_lower = term.lower().strip()
    total_rows = len(pim_df)
    
    # OPTIMIZATION: If pre-computed corpus is provided, use it (much faster)
    if description_corpus is not None:
        # Vectorized search on pre-computed corpus (single operation, no loops!)
        matching_rows = description_corpus.str.contains(term_lower, regex=False, na=False).sum()
    else:
        # Fallback: Row-by-row search (slower, but works without pre-computation)
        if not description_columns:
            return False
        
        matching_rows = 0
        for _, row in pim_df.iterrows():
            found_in_row = False
            for col in description_columns:
                if col in row and pd.notna(row[col]):
                    if term_lower in str(row[col]).lower():
                        found_in_row = True
                        break
            if found_in_row:
                matching_rows += 1
    
    frequency = matching_rows / total_rows if total_rows > 0 else 0
    is_noisy = frequency > NOISE_FREQUENCY_THRESHOLD
    
    print(f"  Noise detection for '{term}': {matching_rows}/{total_rows} rows ({frequency:.1%}) - {'NOISY' if is_noisy else 'SPECIFIC'}")
    
    return is_noisy


def calculate_match_score_weighted(
    row: pd.Series,
    term: str,
    is_noisy: bool,
    column_weights_map: Dict[str, int],
    description_columns: Set[str]
) -> int:
    """
    Calculate weighted match score for a search term in a SKU row.
    
    Args:
        row: DataFrame row containing SKU data
        term: Search term to match
        is_noisy: Whether the term is noisy (from noise detection)
        column_weights_map: Dictionary mapping column names to weights
        description_columns: Set of description column names
    
    Returns:
        int: Total match score
    """
    term_lower = term.lower().strip()
    score = 0
    
    for col_name, value in row.items():
        if pd.isna(value) or not str(value).strip():
            continue
        
        # Get column weight
        weight = column_weights_map.get(col_name, 0)
        
        # If term is noisy, ignore description columns completely
        if is_noisy and col_name in description_columns:
            continue
        
        # Check if term appears in this column's value
        value_lower = str(value).lower()
        if term_lower in value_lower:
            score += weight
    
    return score


def _calculate_sku_count_for_term_weighted(
    pim_df: pd.DataFrame,
    term: str,
    sku_id_column: str,
    description_corpus: pd.Series = None,
    collect_ids: bool = False
) -> Tuple[int, Optional[Set[str]]]:
    """
    Calculate SKU count for a term using the Smart SKU Counting logic.
    
    PERFORMANCE OPTIMIZED: Accepts pre-computed description corpus to avoid row iteration in noise detection.
    
    Args:
        pim_df: DataFrame containing PIM data
        term: Search term
        sku_id_column: Name of SKU ID column
        description_corpus: Pre-computed series of concatenated description text (optional, for performance)
    
    Returns:
        int: Number of SKUs matching the term
    """
    # Step 1: Identify column types
    all_columns = pim_df.columns.tolist()
    description_columns = [col for col in all_columns if _get_column_weight(col) == COLUMN_WEIGHTS['low_confidence']]
    
    # Step 2: Perform noise detection (use pre-computed corpus if available)
    is_noisy = _is_term_noisy(pim_df, term, description_columns, description_corpus)
    
    # Step 3: Set match threshold based on noise
    threshold = 5 if is_noisy else 1
    print(f"  Match threshold for '{term}': {threshold} (term is {'NOISY' if is_noisy else 'SPECIFIC'})")
    
    # Step 4: Build column weights map
    column_weights_map = {col: _get_column_weight(col) for col in all_columns}
    description_columns_set = set(description_columns)
    
    # Step 5: Calculate match scores for each row
    matched_skus = 0
    matched_ids: Set[str] = set() if collect_ids else None
    for _, row in pim_df.iterrows():
        score = calculate_match_score_weighted(
            row, term, is_noisy, column_weights_map, description_columns_set
        )
        if score >= threshold:
            matched_skus += 1
            if collect_ids:
                sku_val = row.get(sku_id_column)
                if pd.notna(sku_val) and str(sku_val).strip():
                    matched_ids.add(str(sku_val).strip())
    
    return matched_skus, matched_ids


def classify_term_by_depth_and_demand(sku_count: int, organic_traffic: float) -> str:
    """
    Classify a term based on SKU Count (Depth) and Traffic Volume (Demand).
    
    Classification Matrix:
    - SKU Count >= 40: "Core Category"
    - SKU Count < 40 AND Traffic >= 1000: "SEO Landing Page"
    - SKU Count < 40 AND Traffic < 1000: "Facet / Filter"
    
    Args:
        sku_count: Number of matching SKUs
        organic_traffic: Monthly organic traffic
    
    Returns:
        str: Recommendation ("Core Category", "SEO Landing Page", or "Facet / Filter")
    """
    if sku_count >= SKU_THRESHOLD_HIGH:
        return "Core Category"
    elif organic_traffic >= TRAFFIC_THRESHOLD_HIGH:
        return "SEO Landing Page"
    else:
        return "Facet / Filter"


def _detect_file_encoding(file_path: str, sample_size: int = 65536) -> Optional[str]:
    """
    Use chardet (if available) to guess the encoding of a text file.
    Returns None when detection is unavailable or confidence is too low.
    """
    if chardet is None:
        return None
    try:
        with open(file_path, 'rb') as fh:
            raw = fh.read(sample_size)
        detection = chardet.detect(raw)
        encoding = detection.get('encoding')
        confidence = detection.get('confidence', 0)
        if encoding and confidence >= 0.5:
            return encoding
    except Exception:
        pass
    return None


def _read_csv_with_encoding_fallback(csv_path: str) -> pd.DataFrame:
    """
    Load a CSV using UTF-8 first, then progressively fall back to detected or
    permissive encodings so PIM exports with exotic characters still load.
    """
    fallback_encodings = ['utf-8', 'utf-8-sig', 'cp1252', 'latin-1']
    last_error = None
    for encoding in fallback_encodings:
        try:
            return pd.read_csv(csv_path, encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    
    detected = _detect_file_encoding(csv_path)
    if detected:
        try:
            print(f"Detected encoding '{detected}' for {csv_path}, applying replacement strategy.")
            return pd.read_csv(csv_path, encoding=detected, errors='replace')
        except UnicodeDecodeError as exc:
            last_error = exc
    
    try:
        print(f"Falling back to latin-1 with ignored errors for {csv_path}.")
        return pd.read_csv(csv_path, encoding='latin-1', errors='ignore')
    except Exception:
        if last_error:
            raise last_error
        raise


def _configure_nlp_model(nlp_model):
    """Apply tokenizer and stop-word safeguards required for prefix protection."""
    if nlp_model is None:
        return
    _remove_protected_prefix_stopwords(nlp_model)
    _configure_tokenizer_for_prefixes(nlp_model)


def _remove_protected_prefix_stopwords(nlp_model):
    """Ensure semantic prefixes are never stripped as stop-words."""
    if nlp_model is None:
        return
    for prefix in PROTECTED_PREFIXES:
        if prefix in nlp_model.Defaults.stop_words:
            nlp_model.Defaults.stop_words.remove(prefix)
        lex = nlp_model.vocab[prefix]
        lex.is_stop = False


def _configure_tokenizer_for_prefixes(nlp_model):
    """Treat underscores as part of tokens so fused prefixes survive tokenization."""
    if nlp_model is None:
        return
    infixes = [pattern for pattern in nlp_model.Defaults.infixes if '_' not in pattern]
    infix_regex = compile_infix_regex(tuple(infixes))
    tokenizer = nlp_model.tokenizer
    nlp_model.tokenizer = Tokenizer(
        nlp_model.vocab,
        rules=nlp_model.Defaults.tokenizer_exceptions,
        prefix_search=tokenizer.prefix_search,
        suffix_search=tokenizer.suffix_search,
        infix_finditer=infix_regex.finditer,
        token_match=tokenizer.token_match
    )


def _fuse_semantic_prefixes(text: str) -> str:
    """Fuse protected prefixes with the succeeding token for consistent downstream matching."""
    if not text:
        return text

    def _replace(match):
        return f"{match.group(1)}_{match.group(2)}"

    return PREFIX_FUSION_REGEX.sub(_replace, text)


@lru_cache(maxsize=4096)
def _compile_negation_guard_pattern(token: str) -> Optional[re.Pattern]:
    """Compile and cache a negative lookbehind guarded regex for a token."""
    token = token.strip().lower()
    if not token:
        return None
    escaped = re.escape(token)
    pattern = NEGATIVE_LOOKBEHIND_PATTERN + r'\b' + escaped + r'\b'
    return re.compile(pattern, re.IGNORECASE)


def _passes_negation_guard(target_value: str, text: str) -> bool:
    """
    Return True if at least one token from target_value appears in text without a negative prefix.
    Reject matches that only occur in explicit negative contexts (e.g., "not plastic").
    """
    if not target_value or not text:
        return False
    
    normalized_tokens = _normalize_value(target_value).split()
    if not normalized_tokens:
        normalized_tokens = [target_value.lower().strip()]
    
    text_lower = text.lower()
    found_any_occurrence = False
    for token in normalized_tokens:
        pattern = _compile_negation_guard_pattern(token)
        token_regex = re.compile(r'\b' + re.escape(token) + r'\b', re.IGNORECASE)
        matches = list(token_regex.finditer(text_lower))
        if matches:
            found_any_occurrence = True
        for match in matches:
            window_start = max(0, match.start() - 40)
            window = text_lower[window_start:match.start()]
            window_has_negation = any(
                re.search(r'\b' + neg + r'(?:\b|[-\s])', window, re.IGNORECASE)
                for neg in NEGATIVE_WINDOW_TERMS
            )
            scope_start = max(0, match.start() - 10)
            scope = text_lower[scope_start:match.end()]
            passes_lookbehind = True
            if pattern:
                passes_lookbehind = bool(pattern.search(scope))
            if passes_lookbehind and not window_has_negation:
                return True
    return False


def _accept_positive_match(target_value: str, context_text: str) -> bool:
    """Return True only when the candidate occurrence survives the negation guard."""
    if not context_text:
        return False
    return _passes_negation_guard(target_value, context_text)


# Try to load spaCy NLP model for intelligent matching
try:
    nlp = spacy.load("en_core_web_md")
    _configure_nlp_model(nlp)
except OSError:
    try:
        subprocess.run([sys.executable, "-m", "spacy", "download", "en_core_web_md"], check=True)
        nlp = spacy.load("en_core_web_md")
        _configure_nlp_model(nlp)
    except (subprocess.CalledProcessError, OSError):
        print("Warning: spaCy model not available. Intelligent matching will be limited.")
        nlp = None


def calculate_sku_counts_for_terms(
    pim_csv_path: str,
    terms: List[str],
    sku_id_column: str = None,
    progress_reporter: callable = None,
    include_sku_ids: bool = True
) -> Dict[str, Dict]:
    """
    Calculate SKU counts for a list of terms using Smart SKU Counting logic.
    
    This function uses weighted scoring and noise detection to provide accurate
    SKU counts that eliminate false positives (e.g., "Spray Paint" mentioned
    in description of "Masonry Paint").
    
    PERFORMANCE OPTIMIZED: Pre-computes description corpus once for all terms.
    
    Args:
        pim_csv_path: Path to the PIM CSV file
        terms: List of search terms to count SKUs for
        sku_id_column: Name of the SKU ID column (auto-detected if None)
        progress_reporter: Optional callback for progress reporting
    
    Returns:
        Dict[str, int]: Dictionary mapping terms to SKU counts
    """
    try:
        # Load PIM CSV with encoding fallback
        pim_df = _read_csv_with_encoding_fallback(pim_csv_path)
        
        if progress_reporter:
            progress_reporter("Loading PIM data for SKU counting...", 0, len(terms))
        
        # Clean the dataframe
        pim_df = _clean_pim_dataframe(pim_df)
        
        # Auto-detect SKU ID column if not provided
        if sku_id_column is None:
            sku_id_column = _detect_sku_column(pim_df)
        
        if sku_id_column is None or sku_id_column not in pim_df.columns:
            raise ValueError(f"SKU ID column '{sku_id_column}' not found in PIM CSV")
        
        print(f"\n=== Smart SKU Counting ===")
        print(f"Processing {len(terms)} terms against {len(pim_df)} SKUs")
        print(f"Using weighted scoring with noise detection\n")
        
        # OPTIMIZATION: Pre-calculate description corpus ONCE (not per term!)
        # This dramatically improves performance for multiple terms
        all_columns = pim_df.columns.tolist()
        description_columns = [col for col in all_columns if _get_column_weight(col) == COLUMN_WEIGHTS['low_confidence']]
        
        if description_columns:
            print(f"Pre-computing description corpus from columns: {description_columns}")
            # Create a single series of lowercase description text for fast searching
            description_corpus = pim_df[description_columns].apply(
                lambda x: ' '.join(x.astype(str)), axis=1
            ).str.lower()
            print(f"Description corpus ready ({len(description_corpus)} rows)\n")
        else:
            description_corpus = None
        
        # Calculate SKU count for each term
        results = {}
        for idx, term in enumerate(terms):
            if progress_reporter and idx % 10 == 0:
                progress_reporter(f"Calculating SKU counts: {idx}/{len(terms)}", idx, len(terms))
            
            print(f"[{idx+1}/{len(terms)}] Analyzing term: '{term}'")
            sku_count, sku_ids = _calculate_sku_count_for_term_weighted(
                pim_df,
                term,
                sku_id_column,
                description_corpus,
                collect_ids=include_sku_ids
            )
            results[term] = {
                'count': sku_count,
                'sku_ids': list(sku_ids) if include_sku_ids and sku_ids is not None else None
            }
            print(f"  → SKU Count: {sku_count} (ids collected: {include_sku_ids and sku_ids is not None})\n")
        
        if progress_reporter:
            progress_reporter("SKU counting complete", len(terms), len(terms))
        
        return results
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise ValueError(f"Failed to calculate SKU counts: {str(e)}")


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
        # Load PIM CSV file with encoding fallbacks so exotic exports don't fail
        pim_df = _read_csv_with_encoding_fallback(pim_csv_path)
        
        if progress_reporter:
            progress_reporter("Cleaning PIM data (removing HTML + normalizing text)...", 0, 100)
        pim_df = _clean_pim_dataframe(pim_df)
        all_columns = pim_df.columns.tolist()
        
        # Auto-detect SKU ID column if not provided
        if sku_id_column is None:
            sku_id_column = _detect_sku_column(pim_df)
        
        if sku_id_column is None or sku_id_column not in pim_df.columns:
            raise ValueError(f"SKU ID column '{sku_id_column}' not found in PIM CSV")
        
        # DEBUG: Log incoming category-facet map
        print(f"\n[DEBUG] Received {len(category_facet_map)} category-facet pairs from frontend")
        climb_pairs = [p for p in category_facet_map if p.get('Category Mapping', '').strip() and 'climb' in p.get('Category Mapping', '').lower()]
        if climb_pairs:
            print(f"[DEBUG] Found {len(climb_pairs)} pairs with 'climb' in category name:")
            for p in climb_pairs:
                print(f"  - Category: '{p.get('Category Mapping')}', Facet Attr: '{p.get('Facet Attribute')}', Facet Val: '{p.get('Facet Value')}'")
        else:
            print(f"[DEBUG] WARNING: No pairs found with 'climb' in category name!")
            # Show first 10 categories for debugging
            sample_cats = [p.get('Category Mapping', '') for p in category_facet_map[:10]]
            print(f"[DEBUG] Sample categories received: {sample_cats}")
        
        # Normalize category-facet map
        category_facet_pairs = _normalize_category_facet_map(category_facet_map)
        
        # DEBUG: Log after normalization
        climb_pairs_norm = [p for p in category_facet_pairs if p.get('Category Mapping', '').strip() and 'climb' in p.get('Category Mapping', '').lower()]
        if climb_pairs_norm:
            print(f"[DEBUG] After normalization, found {len(climb_pairs_norm)} pairs with 'climb':")
            for p in climb_pairs_norm:
                print(f"  - Category: '{p.get('Category Mapping')}', Facet Attr: '{p.get('Facet Attribute')}', Facet Val: '{p.get('Facet Value')}'")
        
        # Extract known values from category-facet map
        known_categories = set()
        known_facet_values = defaultdict(set)  # Maps facet type to set of values
        facet_value_domains = defaultdict(set)  # Track facet value diversity per attribute
        
        for pair in category_facet_pairs:
            cat = pair.get('Category Mapping', '').strip()
            facet_val = pair.get('Facet Value', '').strip()
            facet_attr = pair.get('Facet Attribute', '').strip().lower()
            if cat:
                known_categories.add(cat.lower())
            if facet_val:
                # Infer facet type from context (this is a simplified approach)
                facet_type = _infer_facet_type(facet_val)
                known_facet_values[facet_type].add(facet_val.lower())
            if facet_attr and facet_attr not in ['(blank)', 'root category']:
                facet_val_lower = facet_val.lower()
                if facet_val_lower and facet_val_lower != '(blank)':
                    facet_value_domains[facet_attr].add(facet_val_lower)
        
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
        brand_columns = [col for col in all_columns if any(term in col.lower() for term in ['brand', 'make', 'manufacturer'])]
        category_columns = [col for col in all_columns if any(term in col.lower() for term in ['category', 'type']) and not re.search(r'product.*type', col.lower())]
        tier1_columns, tier2_columns = _derive_tiered_columns(all_columns)
        column_profiles = _map_columns_to_facets(pim_df)
        prepared_pairs = _prepare_category_facet_pairs(
            category_facet_pairs,
            all_columns,
            column_embeddings_cache,
            facet_attribute_embeddings_cache,
            column_profiles,
            nlp,
            facet_value_domains,
            tier2_columns if tier2_columns else all_columns
        )
        
        # Match SKUs to category-facet combinations
        # Add progress reporting for large files
        sku_matches = []
        print(f"Starting PIM analysis: {total_rows} SKUs to process against {len(prepared_pairs)} category-facet combinations")
        
        # Pre-process SKU text embeddings for faster matching (PERFORMANCE OPTIMIZATION)
        # Process each SKU once and cache its text embeddings - ALL COLUMNS, ALL TEXT
        if progress_reporter:
            progress_reporter("Pre-processing SKU text embeddings (all columns, full text)...", 10, total_rows + 100)
        
        print("Pre-processing SKU text embeddings (all columns, full text)...")
        sku_text_cache = {}
        sku_id_index = all_columns.index(sku_id_column)
        for idx, row_tuple in enumerate(pim_df.itertuples(index=False, name=None)):
            if progress_reporter and idx % 50 == 0:
                progress_reporter(f"Pre-processing SKU {idx}/{total_rows}...", 10 + idx, total_rows + 100)
            
            try:
                row_values = row_tuple
                sku_id = row_values[sku_id_index]
                if pd.isna(sku_id) or not str(sku_id).strip():
                    continue
                
                column_texts = {}
                sku_text_parts = []
                for col_name, cell in zip(all_columns, row_values):
                    if pd.isna(cell):
                        continue
                    cell_value = str(cell).strip()
                    if not cell_value:
                        continue
                    sku_text_parts.append(cell_value)
                    if len(cell_value) > 5:
                        normalized_cell = _normalize_value(cell_value)
                        column_texts[col_name] = {
                            'raw': cell_value,
                            'lower': cell_value.lower(),
                            'normalized': normalized_cell,
                            'multi_values': None
                        }
                if not sku_text_parts:
                    continue
                
                sku_text_combined = ' '.join(sku_text_parts).lower()
                cache_entry = {
                    'text': sku_text_combined,
                    'embedding': None,
                    'keywords': [],
                    'normalized_text': _normalize_value(sku_text_combined),
                    'column_texts': column_texts or {}
                }
                
                if nlp is not None and sku_text_combined and len(sku_text_combined) > 10:
                    try:
                        sku_doc = nlp(sku_text_combined)
                        cache_entry['embedding'] = sku_doc.vector
                        cache_entry['keywords'] = [
                            token.lemma_.lower()
                            for token in sku_doc
                            if not token.is_stop and token.is_alpha
                        ]
                    except Exception:
                        cache_entry['embedding'] = None
                        cache_entry['keywords'] = []
                
                sku_text_cache[str(sku_id)] = cache_entry
            except Exception:
                continue
        
        print(f"Pre-processed {len(sku_text_cache)} SKU text embeddings")
        
        if progress_reporter:
            progress_reporter("Starting SKU matching...", total_rows + 20, total_rows + 100)
        
        # Now match SKUs to category-facet combinations using cached embeddings
        # Process ALL columns and ALL text within cells for full semantic matching
        print("Matching SKUs to category-facet combinations (processing all columns and full text)...")
        print(f"Total comparisons to make: {total_rows} SKUs × {len(prepared_pairs)} combinations = {total_rows * len(prepared_pairs)}")
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
                    prepared_pairs, 
                    knowledge_base,
                    all_columns,  # Process ALL columns
                    brand_columns,
                    category_columns,
                    embedding_cache,  # Pass pre-computed embeddings
                    sku_text_data,  # Pass pre-processed SKU text data (full text from all columns)
                    column_embeddings_cache,  # Pass pre-computed column name embeddings (facet attribute matching)
                    nlp,  # Pass NLP model for semantic matching
                    facet_attribute_embeddings_cache,  # Pass pre-computed facet attribute embeddings
                    tier1_columns,
                    tier2_columns,
                    column_profiles,
                    facet_value_domains
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
        
        # DEBUG: Log all categories being processed
        all_categories = set()
        for pair in prepared_pairs:
            cat = pair.get('Category Mapping', '').strip()
            if cat and 'climb' in cat.lower():
                print(f"[DEBUG] Found category with 'climb': '{cat}'")
            all_categories.add(cat)
        print(f"[DEBUG] Total unique categories in map: {len(all_categories)}")
        if 'Anti Climb Paint' in all_categories or 'Anti_Climb Paint' in all_categories or any('climb' in c.lower() for c in all_categories):
            climb_cats = [c for c in all_categories if 'climb' in c.lower()]
            print(f"[DEBUG] Categories containing 'climb': {climb_cats}")
        
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
        
        # DEBUG: Check if Anti Climb Paint got any matches
        climb_results = [r for r in result_list if 'climb' in r.get('Category Mapping', '').lower()]
        if climb_results:
            print(f"\n[DEBUG] Anti Climb Paint results in final output:")
            for r in climb_results:
                print(f"  - {r.get('Category Mapping')}: {r.get('SKU Count')} SKUs, IDs: {r.get('SKU IDs')}")
        else:
            print(f"\n[DEBUG] WARNING: No 'Anti Climb Paint' results in final output!")
            # Check what categories DID get matches
            all_cats_with_matches = set(r.get('Category Mapping') for r in result_list if r.get('SKU Count', 0) > 0)
            print(f"[DEBUG] Categories that DID get matches (sample): {list(all_cats_with_matches)[:10]}")
        
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
    """
    Normalize category-facet map data.
    
    NOTE: We preserve the original category name format here - normalization happens
    during matching, not here. This ensures the category name in results matches
    what was in the original Category Overhaul Matrix.
    """
    normalized = []
    for item in category_facet_map:
        # Preserve original category name - don't fuse prefixes here
        # The matching logic will handle normalization during comparison
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
    - Various separators (/, |, \\, etc.)
    - Other punctuation that acts as separators
    """
    if not value:
        return ''
    
    # Preserve critical phrases before any normalization so they survive stop-word removal
    protected_value = _apply_phrase_protection(str(value))
    protected_value = _fuse_semantic_prefixes(protected_value)
    
    # Convert to lowercase after protection
    normalized = protected_value.lower().strip()
    
    # Replace ALL separators (hyphens, underscores, slashes, etc.) with spaces
    # This ensures "Anti-Climb", "Anti_Climb", and "Anti Climb" all normalize to "anti climb"
    normalized = re.sub(r'[-_/\\|]+', ' ', normalized)
    
    # Remove trailing/leading punctuation
    normalized = re.sub(r'[.,;:]+(?=\s|$)|(?<=\s)[.,;:]+', '', normalized)
    
    # Replace remaining special characters with spaces (but preserve alphanumeric and spaces)
    normalized = re.sub(r'[^\w\s]', ' ', normalized)
    
    # Convert underscores to spaces (underscores are word chars but we want spaces for consistency)
    normalized = normalized.replace('_', ' ')
    
    # Collapse multiple spaces into single space and trim
    normalized = ' '.join(normalized.split())
    
    return normalized


def _should_debug_category(category: Optional[str]) -> bool:
    """Return True when verbose debugging is enabled for the given category."""
    if not VERBOSE_CATEGORY_DEBUG or not category:
        return False
    keyword = DEBUG_CATEGORY_KEYWORD
    if not keyword:
        return True
    return keyword in category.lower()


PROTECTED_PHRASES = [
    'anti-climb',
    'anti-slip',
    'anti-rust',
    'spray-paint',
    'non-drip'
]

NEGATIVE_CONTEXT_PREFIXES = (
    'not suitable for',
    'except',
    'non-',
    'non ',
    'no '
)

TIER1_IDENTITY_COLUMNS = {
    'part name',
    'product brand name',
    'part name type',
    'toolstation web copy',
    'toolstation catalogue copy',
    'ts product code'
}

TIER2_DESCRIPTIVE_COLUMNS = {
    'supplier copy',
    'description',
    'application method',
    'suitable for',
    'substrate'
}

VOLUME_PATTERN = re.compile(r'\b\d+(\.\d+)?\s*(ml|l|litres|gal|fl\s?oz)\b', re.IGNORECASE)
DIMENSION_PATTERN = re.compile(r'\d+\s*(mm|cm|m|in|ft)\s*[xX]\s*\d+', re.IGNORECASE)
WEIGHT_PATTERN = re.compile(r'\b\d+(\.\d+)?\s*(kg|g|lbs?|oz)\b', re.IGNORECASE)
BOOLEAN_VALUES = {'yes', 'no', 'true', 'false', 'y', 'n'}


def _apply_phrase_protection(value: str) -> str:
    """Ensure protected phrases such as 'anti-climb' remain intact during tokenization."""
    if not value:
        return value
    
    protected = value
    for phrase in PROTECTED_PHRASES:
        # Build regex that matches hyphenated or spaced variants of the phrase
        phrase_parts = re.split(r'[-\s]+', phrase)
        flexible_pattern = r'\s*[-\s]?\s*'.join(map(re.escape, phrase_parts))
        regex = re.compile(flexible_pattern, re.IGNORECASE)
        
        def _replace(match):
            matched_text = match.group(0)
            normalized = re.sub(r'[-\s]+', '_', matched_text.strip())
            return normalized
        
        protected = regex.sub(_replace, protected)
    return protected


def _split_multi_value_cell(cell_value: str) -> List[str]:
    """
    Split a cell into multiple values using smart delimiters.
    Handles semicolons, pipes, newlines, and commas that are not numeric thousands separators.
    """
    if not cell_value:
        return []
    
    tokens = re.split(r'[;|,\n]', cell_value)
    return [token.strip() for token in tokens if token and token.strip()]


def _strip_negative_context(text: str) -> str:
    """Remove clauses that begin with negative qualifiers like 'Not suitable for'."""
    if not text:
        return text
    
    clauses = re.split(r'[.;\n]|(?:\s{2,})', text)
    kept = []
    for clause in clauses:
        clause_clean = clause.strip()
        if not clause_clean:
            continue
        lowered = clause_clean.lower()
        if any(lowered.startswith(prefix) for prefix in NEGATIVE_CONTEXT_PREFIXES):
            continue
        kept.append(clause_clean)
    return ' '.join(kept)


def _derive_tiered_columns(all_columns: List[str]) -> Tuple[List[str], List[str]]:
    """Return concrete Tier 1 and Tier 2 column lists using case-insensitive matching."""
    tier1 = []
    tier2 = []
    seen = set()
    
    for col in all_columns:
        col_lower = col.lower()
        if col in seen:
            continue
        seen.add(col)
        if col_lower in TIER1_IDENTITY_COLUMNS:
            tier1.append(col)
        elif col_lower in TIER2_DESCRIPTIVE_COLUMNS:
            tier2.append(col)
    
    # Any column not explicitly marked as Tier1 goes into Tier2 by default
    for col in all_columns:
        if col not in tier1 and col not in tier2:
            tier2.append(col)
    
    return tier1, tier2


CATEGORY_GENERIC_TERMS = {
    'paint', 'paints', 'anti', 'the', 'and', 'with', 'for', 'coat', 'coats',
    'coating', 'coatings', 'finish', 'finishes', 'color', 'colour', 'type',
    'types', 'category', 'categories', 'group', 'groups', 'product', 'products',
    'range', 'ranges', 'pro', 'plus', 'ultra', 'super', 'extra', 'new', 'all',
    'any', 'multi', 'surface', 'surfaces', 'solution', 'solutions', 'system',
    'systems', 'set', 'sets', 'collection', 'collections', 'series', 'black',
    'white', 'grey', 'gray', 'coat', 'coating', 'spray', 'primer', 'gloss'
}


def _extract_significant_words(words: List[str]) -> List[str]:
    """Return words that carry real meaning (exclude generic category terms)."""
    return [w for w in words if len(w) >= 3 and w not in CATEGORY_GENERIC_TERMS]


def _category_required_tokens(category: str) -> List[str]:
    """
    Return normalized, non-generic tokens that must appear for a category match.
    
    Preserves prefixed phrases (e.g., "anti climb") even if the prefix is generic,
    since the combination is meaningful.
    """
    if not category:
        return []
    normalized = _normalize_value(category)
    tokens = normalized.split()
    
    # Check for prefixed phrases (e.g., "anti climb", "non drip")
    # These should be preserved as phrases even if the prefix is generic
    required = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        # Check if this token is a protected prefix and next token exists
        if token in PROTECTED_PREFIXES and i + 1 < len(tokens):
            next_token = tokens[i + 1]
            # Create phrase: "anti climb", "non drip", etc.
            phrase = f"{token} {next_token}"
            required.append(phrase)
            i += 2  # Skip both tokens
        else:
            # Regular word - check if it's significant
            if len(token) >= 3 and token not in CATEGORY_GENERIC_TERMS:
                required.append(token)
            i += 1
    
    return required if required else _extract_significant_words(tokens)  # Fallback to original logic


def _category_tokens_present(required_tokens: List[str], sku_text_normalized: str, tier1_values: List[str] = None) -> bool:
    """
    Check whether all required tokens exist in SKU text or tier1 fields.
    
    Since all text is normalized to space-separated words, we can check for exact word matches.
    For multi-word tokens (e.g., "anti climb"), we check if the phrase appears or all words are present.
    """
    if not required_tokens:
        return True
    normalized_text = sku_text_normalized or ''
    
    # DEBUG: Log token checking for anti climb
    debug_tokens = any('climb' in token.lower() for token in required_tokens)

    # Check if all tokens appear in normalized text
    # For space-separated tokens, check if the phrase appears or all words are present
    if normalized_text:
        all_present = True
        for token in required_tokens:
            # Token is already normalized (space-separated words)
            # Check if token phrase appears, or if all words in token appear
            token_words = token.split()
            if len(token_words) > 1:
                # Multi-word token: check if phrase appears or all words are present
                phrase_present = token in normalized_text
                words_present = all(word in normalized_text for word in token_words)
                if debug_tokens:
                    print(f"    [DEBUG TOKEN] '{token}': phrase_present={phrase_present}, words_present={words_present}, words={token_words}")
                if not (phrase_present or words_present):
                    all_present = False
                    if debug_tokens:
                        print(f"    [DEBUG TOKEN] ✗ Token '{token}' NOT found")
                    break
                elif debug_tokens:
                    print(f"    [DEBUG TOKEN] ✓ Token '{token}' found")
            else:
                # Single word token: check if word appears
                word_present = token in normalized_text
                if debug_tokens:
                    print(f"    [DEBUG TOKEN] '{token}': present={word_present}")
                if not word_present:
                    all_present = False
                    if debug_tokens:
                        print(f"    [DEBUG TOKEN] ✗ Token '{token}' NOT found")
                    break
                elif debug_tokens:
                    print(f"    [DEBUG TOKEN] ✓ Token '{token}' found")
        if all_present:
            if debug_tokens:
                print(f"  [DEBUG] All tokens found in normalized text")
            return True
        elif debug_tokens:
            print(f"  [DEBUG] Some tokens missing in normalized text")
    
    # Also check tier1 fields
    for value in tier1_values or []:
        if not value:
            continue
        normalized_value = _normalize_value(value)
        all_present = True
        for token in required_tokens:
            token_words = token.split()
            if len(token_words) > 1:
                phrase_present = token in normalized_value
                words_present = all(word in normalized_value for word in token_words)
                if not (phrase_present or words_present):
                    all_present = False
                    break
            else:
                if token not in normalized_value:
                    all_present = False
                    break
        if all_present:
            if debug_tokens:
                print(f"  [DEBUG] All tokens found in tier1 fields")
            return True
        elif debug_tokens:
            print(f"  [DEBUG] Some tokens missing in tier1 fields")
    if debug_tokens:
        print(f"  [DEBUG] ✗ Tokens NOT present - returning False")
    return False


def _clean_pim_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean PIM data by stripping placeholder HTML tags, decoding entities, and normalizing whitespace.
    Applied once during import so downstream matching works with consistent text.
    """
    if df is None or df.empty:
        return df
    
    cleaned_df = df.copy()
    object_cols = cleaned_df.select_dtypes(include=['object']).columns
    if not len(object_cols):
        return cleaned_df
    
    for col in object_cols:
        cleaned_df[col] = cleaned_df[col].apply(_clean_cell_text)
    
    return cleaned_df


def _clean_cell_text(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return value
    
    if isinstance(value, (int, np.integer, float, np.floating)) and not isinstance(value, (bool, np.bool_)):
        return value
    
    text = str(value)
    if not text.strip():
        return ''
    
    text = text.replace('<lt/>', '<').replace('<gt/>', '>')
    text = html.unescape(text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = text.replace('\u00a0', ' ')
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return _fuse_semantic_prefixes(text)


def _map_columns_to_facets(pim_df: pd.DataFrame) -> Dict[str, Dict]:
    """
    Build lightweight profiles for each column so facet attribute matching
    can consider the underlying data when headers are ambiguous.
    """
    profiles = {}
    if pim_df is None or pim_df.empty:
        return profiles
    
    for col in pim_df.columns:
        series = pim_df[col].dropna()
        samples = []
        for val in series:
            val_str = str(val).strip()
            if val_str:
                samples.append(val_str)
            if len(samples) >= 10:
                break
        if not samples:
            continue
        
        pattern_scores = _compute_column_pattern_scores(samples)
        boolean_ratio = _compute_boolean_ratio(samples)
        profiles[col] = {
            'samples': samples,
            'pattern_scores': pattern_scores,
            'boolean_ratio': boolean_ratio
        }
    return profiles


def _prepare_category_facet_pairs(
    category_facet_pairs: List[Dict],
    all_columns: List[str],
    column_embeddings_cache: Optional[Dict[str, Dict]] = None,
    facet_attribute_embeddings_cache: Optional[Dict[str, Dict]] = None,
    column_profiles: Optional[Dict[str, Dict]] = None,
    nlp_model=None,
    facet_value_domains: Optional[Dict[str, Set[str]]] = None,
    fallback_columns: Optional[List[str]] = None
) -> List[Dict]:
    """Pre-compute expensive metadata for each category-facet pair once."""
    if not category_facet_pairs:
        return []
    
    fallback_columns = fallback_columns or all_columns
    prepared_pairs = []
    
    for pair in category_facet_pairs:
        category = pair.get('Category Mapping', '').strip()
        facet_attribute = pair.get('Facet Attribute', '').strip()
        facet_value = pair.get('Facet Value', '').strip()
        
        facet_attribute_lower = facet_attribute.lower().strip() if facet_attribute else ''
        is_root_category = (facet_attribute == 'Root Category' or facet_value == 'Root Category')
        facet_attribute_is_blank = (not facet_attribute) or facet_attribute in ('(Blank)', 'Root Category')
        
        category_required_tokens = _category_required_tokens(category)
        if facet_attribute_is_blank:
            relevant_columns = list(all_columns)
            attribute_used_fallback = False
        else:
            relevant_columns, attribute_used_fallback = _resolve_facet_attribute_columns(
                facet_attribute_lower,
                all_columns,
                column_embeddings_cache,
                facet_attribute_embeddings_cache,
                column_profiles,
                nlp_model,
                fallback_columns
            )
        
        is_discrete = False
        if facet_value_domains is not None and not is_root_category:
            is_discrete = _is_discrete_facet_attribute(facet_attribute_lower, facet_value_domains)
        
        prepared_entry = dict(pair)
        prepared_entry['_category_required_tokens'] = category_required_tokens
        prepared_entry['_is_root_category'] = is_root_category
        prepared_entry['_facet_attribute_lower'] = facet_attribute_lower
        prepared_entry['_facet_attribute_is_blank'] = facet_attribute_is_blank
        prepared_entry['_facet_relevant_columns'] = tuple(relevant_columns)
        prepared_entry['_facet_attribute_used_fallback'] = attribute_used_fallback
        prepared_entry['_is_discrete_facet'] = is_discrete
        prepared_pairs.append(prepared_entry)
    
    return prepared_pairs


def _resolve_facet_attribute_columns(
    facet_attribute_lower: str,
    all_columns: List[str],
    column_embeddings_cache: Optional[Dict[str, Dict]],
    facet_attribute_embeddings_cache: Optional[Dict[str, Dict]],
    column_profiles: Optional[Dict[str, Dict]],
    nlp_model,
    fallback_columns: List[str]
) -> Tuple[List[str], bool]:
    """Resolve which columns best align with a facet attribute using semantic cues."""
    if not facet_attribute_lower or facet_attribute_lower in ('(blank)', 'root category'):
        return list(all_columns), False
    
    matching_columns: List[str] = []
    facet_intent = _facet_attribute_intent(facet_attribute_lower)
    
    def _boost_similarity(column_name: str, score: float) -> float:
        if not column_profiles or not facet_intent:
            return score
        if not (0.4 < score < 0.85):
            return score
        profile = column_profiles.get(column_name)
        if profile and _column_profile_matches_intent(profile, facet_intent):
            return 1.0
        return score
    
    attr_embedding = None
    attr_keywords: List[str] = []
    attr_norm = 0.0
    
    if nlp_model is not None:
        try:
            if facet_attribute_embeddings_cache and facet_attribute_lower in facet_attribute_embeddings_cache:
                attr_data = facet_attribute_embeddings_cache[facet_attribute_lower]
                attr_embedding = attr_data['embedding']
                attr_keywords = attr_data.get('keywords', [])
                attr_norm = attr_data.get('norm', np.linalg.norm(attr_embedding))
            else:
                attr_doc = nlp_model(facet_attribute_lower)
                attr_embedding = attr_doc.vector
                attr_keywords = [token.lemma_.lower() for token in attr_doc if not token.is_stop and token.is_alpha]
                attr_norm = np.linalg.norm(attr_embedding)
        except Exception:
            attr_embedding = None
            attr_keywords = []
            attr_norm = 0.0
    
    if attr_embedding is not None and attr_norm > 0:
        cache_source = column_embeddings_cache
        if cache_source is None:
            cache_source = {}
            for col in all_columns:
                try:
                    col_doc = nlp_model(col.lower())
                    cache_source[col] = {
                        'embedding': col_doc.vector,
                        'keywords': [token.lemma_.lower() for token in col_doc if not token.is_stop and token.is_alpha]
                    }
                except Exception:
                    continue
        
        for col, col_data in cache_source.items():
            try:
                col_embedding = col_data['embedding']
                col_keywords = col_data.get('keywords', [])
                col_norm = np.linalg.norm(col_embedding)
                if col_norm == 0:
                    continue
                similarity = np.dot(attr_embedding, col_embedding) / (attr_norm * col_norm)
                similarity = _boost_similarity(col, similarity)
                if similarity >= 0.65:
                    if attr_keywords and col_keywords:
                        matching_keywords = sum(1 for kw in attr_keywords if kw in col_keywords)
                        ratio = matching_keywords / len(attr_keywords) if attr_keywords else 0
                        if ratio >= 0.3 or similarity >= 0.80:
                            matching_columns.append(col)
                    elif similarity >= 0.80:
                        matching_columns.append(col)
            except Exception:
                continue
    
    # Fallback to normalized header comparisons
    if not matching_columns:
        attr_normalized = facet_attribute_lower.replace('_', ' ').replace('-', ' ').replace(' ', '').strip()
        for col in all_columns:
            col_normalized = col.lower().replace('_', ' ').replace('-', ' ').replace(' ', '').strip()
            if (attr_normalized and (
                attr_normalized == col_normalized or
                attr_normalized in col_normalized or
                col_normalized in attr_normalized
            )):
                matching_columns.append(col)
    
    # Pattern override using column profiles
    if not matching_columns and facet_intent and column_profiles:
        pattern_matches = [
            col_name for col_name, profile in column_profiles.items()
            if _column_profile_matches_intent(profile, facet_intent)
        ]
        matching_columns.extend(pattern_matches)
    
    if matching_columns:
        unique_columns = list(dict.fromkeys(matching_columns))
        return unique_columns, False
    
    return list(dict.fromkeys(fallback_columns)), True


def _compute_column_pattern_scores(samples: List[str]) -> Dict[str, float]:
    """Calculate how often sample values match known facet patterns."""
    scores = {'volume': 0.0, 'dimensions': 0.0, 'weight': 0.0}
    if not samples:
        return scores
    
    total = len(samples)
    volume_hits = sum(1 for val in samples if VOLUME_PATTERN.search(val))
    dimension_hits = sum(1 for val in samples if DIMENSION_PATTERN.search(val))
    weight_hits = sum(1 for val in samples if WEIGHT_PATTERN.search(val))
    
    scores['volume'] = volume_hits / total
    scores['dimensions'] = dimension_hits / total
    scores['weight'] = weight_hits / total
    return scores


def _compute_boolean_ratio(samples: List[str]) -> float:
    """Return the ratio of boolean-like values in the sample."""
    if not samples:
        return 0.0
    normalized = [str(val).strip().lower() for val in samples]
    bool_hits = sum(1 for val in normalized if val in BOOLEAN_VALUES)
    return bool_hits / len(normalized)


def _column_profile_matches_intent(profile: Dict, intent: str) -> bool:
    """Check whether the column profile confidently matches the desired facet intent."""
    if not profile or not intent:
        return False
    if intent == 'boolean':
        return profile.get('boolean_ratio', 0.0) >= 0.5
    pattern_scores = profile.get('pattern_scores', {})
    return pattern_scores.get(intent, 0.0) >= 0.5


def _facet_attribute_intent(facet_attribute_lower: str) -> Optional[str]:
    """Map a facet attribute to an intent bucket for pattern checks."""
    if not facet_attribute_lower:
        return None
    if any(keyword in facet_attribute_lower for keyword in ['volume', 'capacity', 'litre', 'liter', 'ml']):
        return 'volume'
    if any(keyword in facet_attribute_lower for keyword in ['dimension', 'size', 'height', 'width', 'length']):
        return 'dimensions'
    if 'weight' in facet_attribute_lower:
        return 'weight'
    if any(facet_attribute_lower.startswith(prefix) for prefix in ['is ', 'has ']) or 'boolean' in facet_attribute_lower:
        return 'boolean'
    return None


def _build_negative_context_overrides(sku_row: pd.Series, descriptive_columns: List[str]) -> Dict[str, str]:
    """Return column overrides with exclusionary clauses removed for Tier 2 matching."""
    overrides = {}
    for col in descriptive_columns or []:
        if col in sku_row.index and pd.notna(sku_row[col]):
            original = str(sku_row[col])
            # Preserve multi-value enumerations (e.g., "Masonry;Metal") so delimiters remain intact
            if len(_split_multi_value_cell(original)) > 1:
                continue
            sanitized = _strip_negative_context(original)
            if sanitized != original:
                overrides[col] = sanitized
    return overrides


def _compose_sku_text_with_overrides(
    sku_row: pd.Series,
    overrides: Dict[str, str],
    base_text: Optional[str] = None
) -> str:
    """Rebuild SKU text using overrides for specific columns."""
    if not overrides:
        return base_text if base_text is not None else ''
    
    parts = []
    for col in sku_row.index:
        if col in overrides:
            parts.append(overrides[col])
        else:
            value = sku_row[col]
            if pd.notna(value):
                parts.append(str(value))
    combined = ' '.join(part for part in parts if part).strip()
    if combined:
        return combined.lower()
    return base_text if base_text is not None else ''


def _has_high_confidence_tier1_match(
    target_value: str,
    sku_row: pd.Series,
    tier1_columns: List[str]
) -> bool:
    """Check Tier 1 identity columns for exact or high-overlap matches."""
    if not target_value or not tier1_columns:
        return False
    
    target_normalized = _normalize_value(target_value)
    target_tokens = target_normalized.split()
    target_token_count = len(target_tokens)
    
    for col in tier1_columns:
        if col not in sku_row.index or pd.isna(sku_row[col]):
            continue
        cell_value = str(sku_row[col])
        cell_normalized = _normalize_value(cell_value)
        if not cell_normalized:
            continue
        if target_normalized and target_normalized in cell_normalized:
            return True
        if target_token_count == 0:
            continue
        cell_tokens = cell_normalized.split()
        if not cell_tokens:
            continue
        overlap = len(set(target_tokens) & set(cell_tokens)) / target_token_count
        if overlap >= 0.8:
            return True
    return False


def _is_discrete_facet_attribute(
    facet_attribute_lower: str,
    facet_value_domains: Dict[str, Set[str]]
) -> bool:
    """Determine if a facet attribute should be treated as discrete."""
    if not facet_attribute_lower or not facet_value_domains:
        return False
    values = facet_value_domains.get(facet_attribute_lower)
    if not values:
        return False
    return len(values) <= 20


def _levenshtein_ratio(str1: str, str2: str) -> float:
    """Compute Levenshtein similarity between two strings."""
    len1, len2 = len(str1), len(str2)
    if len1 == 0:
        return 1.0 if len2 == 0 else 0.0
    if len2 == 0:
        return 0.0
    
    matrix = [[0] * (len2 + 1) for _ in range(len1 + 1)]
    for i in range(len1 + 1):
        matrix[i][0] = i
    for j in range(len2 + 1):
        matrix[0][j] = j
    
    for i in range(1, len1 + 1):
        for j in range(1, len2 + 1):
            if str1[i - 1] == str2[j - 1]:
                cost = 0
            else:
                cost = 1
            matrix[i][j] = min(
                matrix[i - 1][j] + 1,
                matrix[i][j - 1] + 1,
                matrix[i - 1][j - 1] + cost
            )
    
    distance = matrix[len1][len2]
    return 1.0 - (distance / max(len1, len2))


def _semantic_similarity(
    text_a: str,
    text_b: str,
    embedding_cache: Optional[Dict[str, np.ndarray]] = None
) -> float:
    """Compute semantic similarity between two strings with optional cache assistance."""
    a_lower = text_a.lower().strip()
    b_lower = text_b.lower().strip()
    vec_a = None
    vec_b = None
    
    if embedding_cache:
        vec_a = embedding_cache.get(a_lower)
        vec_b = embedding_cache.get(b_lower)
    
    if vec_a is not None and vec_b is not None:
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)
        if norm_a > 0 and norm_b > 0:
            return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))
        return 0.0
    
    if nlp is None:
        return 0.0
    
    try:
        doc_a = nlp(a_lower)
        doc_b = nlp(b_lower)
        if doc_a.vector_norm and doc_b.vector_norm:
            return float(doc_a.similarity(doc_b))
    except Exception:
        return 0.0
    
    return 0.0


def _match_discrete_facet_value(
    facet_value: str,
    sku_row: pd.Series,
    relevant_columns: List[str],
    column_text_overrides: Optional[Dict[str, str]],
    embedding_cache: Optional[Dict[str, np.ndarray]]
) -> bool:
    """Apply strict matching logic for discrete facet attributes."""
    if not facet_value:
        return False
    
    target_lower = facet_value.lower().strip()
    target_normalized = _normalize_value(facet_value)
    target_tokens = set(target_normalized.split())
    
    for col in relevant_columns:
        if col not in sku_row.index:
            continue
        raw_value = None
        if column_text_overrides and col in column_text_overrides:
            raw_value = column_text_overrides[col]
        elif pd.notna(sku_row[col]):
            raw_value = str(sku_row[col])
        if not raw_value:
            continue
        
        for candidate in _split_multi_value_cell(raw_value):
            candidate_lower = candidate.lower().strip()
            candidate_normalized = _normalize_value(candidate)
            candidate_tokens = set(candidate_normalized.split())
            
            if (candidate_lower == target_lower or candidate_normalized == target_normalized):
                if _accept_positive_match(facet_value, raw_value):
                    return True
            if target_tokens and candidate_tokens == target_tokens:
                if _accept_positive_match(facet_value, raw_value):
                    return True
            if _levenshtein_ratio(candidate_lower, target_lower) >= 0.9:
                if _accept_positive_match(facet_value, raw_value):
                    return True
            similarity = _semantic_similarity(candidate_lower, target_lower, embedding_cache)
            if similarity >= 0.95 and _accept_positive_match(facet_value, raw_value):
                return True
    return False


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
    facet_attribute_embeddings_cache: Dict = None,
    tier1_columns: List[str] = None,
    tier2_columns: List[str] = None,
    column_profiles: Dict[str, Dict] = None,
    facet_value_domains: Dict[str, Set[str]] = None
) -> List[Dict]:
    """
    Match a single SKU to category-facet combinations with intelligent matching.
    
    This function uses context-aware matching to avoid false positives (e.g., 
    matching "lick" as the brand "Lick" when it appears in other contexts).
    
    Processes ALL columns, ALL rows, and ALL text within cells for maximum accuracy.
    """
    matches = []
    
    # Get all text content from the SKU row (use cached if available)
    if sku_text_data and 'text' in sku_text_data:
        sku_text = sku_text_data['text']
        sku_embedding_cached = sku_text_data.get('embedding')
        sku_keywords_cached = sku_text_data.get('keywords', [])
        sku_text_normalized_full = sku_text_data.get('normalized_text')
    else:
        sku_text = ' '.join([
            str(val) for val in sku_row.values 
            if pd.notna(val) and str(val).strip()
        ]).lower()
        sku_embedding_cached = None
        sku_keywords_cached = None
        sku_text_normalized_full = None
    
    if not sku_text_normalized_full:
        sku_text_normalized_full = _normalize_value(sku_text) if sku_text else ''
        if sku_text_data is not None:
            sku_text_data['normalized_text'] = sku_text_normalized_full

    # Use pre-computed column lists if provided, otherwise compute them
    if brand_columns is None:
        brand_columns = [col for col in all_columns if any(term in col.lower() for term in ['brand', 'make', 'manufacturer'])]
    if category_columns is None:
        category_columns = [col for col in all_columns if any(term in col.lower() for term in ['category', 'type']) and not re.search(r'product.*type', col.lower())]
    
    effective_tier1 = [col for col in (tier1_columns or []) if col in all_columns]
    effective_tier2 = [col for col in (tier2_columns or []) if col in all_columns and col not in effective_tier1]
    if not effective_tier2:
        effective_tier2 = [col for col in all_columns if col not in effective_tier1]
    
    tier2_overrides_cache = _build_negative_context_overrides(sku_row, effective_tier2)
    sanitized_tier2_text = _compose_sku_text_with_overrides(sku_row, tier2_overrides_cache, sku_text)
    tier1_text_samples = [
        str(sku_row[col]) for col in effective_tier1
        if col in sku_row.index and pd.notna(sku_row[col])
    ]
    
    # Get SKU ID for debugging
    sku_id = str(sku_row.get('TS Product Code', sku_row.get('SKU', sku_row.index[0] if len(sku_row) > 0 else 'unknown')))
    debug_category = 'Anti Climb Paint'  # Debug for this specific category
    
    for pair in category_facet_pairs:
        category = pair.get('Category Mapping', '').strip()
        facet_attribute = pair.get('Facet Attribute', '').strip()
        facet_value = pair.get('Facet Value', '').strip()
        facet_attribute_lower = pair.get('_facet_attribute_lower')
        if facet_attribute_lower is None:
            facet_attribute_lower = facet_attribute.lower().strip() if facet_attribute else ''
        
        if not category and not facet_value:
            continue
        
        # Check if this is a "Root Category" match (category only, no facets)
        is_root_category = pair.get('_is_root_category')
        if is_root_category is None:
            is_root_category = (facet_attribute == 'Root Category' or facet_value == 'Root Category')
        category_required_tokens = pair.get('_category_required_tokens')
        if category_required_tokens is None:
            category_required_tokens = _category_required_tokens(category)
        
        debug_enabled = _should_debug_category(category)
        
        # DEBUG: Log details for Anti Climb Paint category
        if debug_enabled:
            print(f"\n[DEBUG SKU {sku_id}] Checking category: '{category}'")
            print(f"  Normalized category: '{_normalize_value(category)}'")
            print(f"  Required tokens: {category_required_tokens}")
            print(f"  SKU normalized text (first 200 chars): '{sku_text_normalized_full[:200]}'")
            print(f"  Tier1 samples: {tier1_text_samples[:3] if tier1_text_samples else []}")
        
        # Match category
        category_matched = False
        if not category or category == '(Blank)':
            category_matched = True
        else:
            tier1_confident = _has_high_confidence_tier1_match(category, sku_row, effective_tier1)
            if tier1_confident:
                category_matched = True
            elif effective_tier1:
                category_matched = _intelligent_match(
                    category,
                    sku_row,
                    sku_text,
                    effective_tier1,
                    knowledge_base,
                    match_type='category',
                    embedding_cache=embedding_cache,
                    sku_embedding_cached=sku_embedding_cached,
                    sku_keywords_cached=sku_keywords_cached,
                    sku_text_data=sku_text_data
                )
            if not category_matched:
                fallback_columns = effective_tier2 if effective_tier2 else all_columns
                category_matched = _intelligent_match(
                    category,
                    sku_row,
                    sku_text,
                    fallback_columns,
                    knowledge_base,
                    match_type='category',
                    embedding_cache=embedding_cache,
                    sku_embedding_cached=sku_embedding_cached,
                    sku_keywords_cached=sku_keywords_cached,
                    sku_text_data=sku_text_data,
                    column_text_overrides=tier2_overrides_cache,
                    sku_text_override=sanitized_tier2_text
                )
        
        # CRITICAL FALLBACK: If _intelligent_match failed but required tokens ARE present,
        # allow the match anyway (catches explicit mentions like "Anti-Climb Paint" in product name)
        tokens_present_before_fallback = None
        if not category_matched and category_required_tokens:
            tokens_present_before_fallback = _category_tokens_present(category_required_tokens, sku_text_normalized_full, tier1_text_samples)
            if tokens_present_before_fallback:
                category_matched = True
                if debug_enabled:
                    print(f"  [DEBUG] Fallback triggered: tokens present, allowing match")
        
        # VALIDATION: If _intelligent_match passed but required tokens are NOT present,
        # reject the match (prevents false positives from semantic similarity alone)
        if category_matched and category_required_tokens:
            tokens_present_after = _category_tokens_present(category_required_tokens, sku_text_normalized_full, tier1_text_samples)
            if not tokens_present_after:
                category_matched = False
                if debug_enabled:
                    print(f"  [DEBUG] Validation failed: tokens NOT present, rejecting match")
        
        # DEBUG: Log final decision for Anti Climb Paint
        if debug_enabled:
            tokens_final = _category_tokens_present(category_required_tokens, sku_text_normalized_full, tier1_text_samples) if category_required_tokens else True
            print(f"  [DEBUG] Final decision: category_matched={category_matched}, tokens_present={tokens_final}, is_root_category={is_root_category}")
        
        # For Root Category, only category match is needed
        if is_root_category:
            if category_matched:
                matches.append({
                    'category': category if category else '(Blank)',
                    'facet_attribute': 'Root Category',
                    'facet_value': 'Root Category'
                })
                if debug_enabled:
                    print(f"  [DEBUG] ✓ MATCHED: Added to matches list")
            else:
                if debug_enabled:
                    print(f"  [DEBUG] ✗ NOT MATCHED: category_matched was False")
            continue  # Skip facet matching for Root Category
        
        # Match facet attribute using pre-computed semantic mapping
        facet_attribute_matched = True
        relevant_columns_for_facet = pair.get('_facet_relevant_columns')
        if relevant_columns_for_facet:
            relevant_columns_for_facet = list(relevant_columns_for_facet)
        if not relevant_columns_for_facet:
            relevant_columns_for_facet = effective_tier2 if effective_tier2 else all_columns
            facet_attribute_used_fallback = True
        else:
            facet_attribute_used_fallback = pair.get('_facet_attribute_used_fallback', False)
        is_discrete_facet = pair.get('_is_discrete_facet')
        if is_discrete_facet is None:
            is_discrete_facet = _is_discrete_facet_attribute(facet_attribute_lower, facet_value_domains)
        
        # Match facet value (only if attribute matched or is Root Category)
        facet_value_matched = False
        if not facet_value or facet_value == '(Blank)' or str(facet_value).strip() == '':
            facet_value_matched = True
        elif facet_attribute_matched:
            facet_column_overrides = {}
            if tier2_overrides_cache and relevant_columns_for_facet:
                facet_column_overrides = {
                    col: tier2_overrides_cache[col]
                    for col in relevant_columns_for_facet
                    if col in tier2_overrides_cache
                }
            # Search in relevant columns (those matching the facet attribute) for maximum accuracy
            # This prevents false positives like "stone" (material) matching "Stone" (colour)
            if is_discrete_facet:
                facet_value_matched = _match_discrete_facet_value(
                    facet_value,
                    sku_row,
                    relevant_columns_for_facet,
                    facet_column_overrides,
                    embedding_cache
                )
            else:
                semantic_threshold = 0.85 if facet_attribute_used_fallback else 0.75
                facet_value_matched = _intelligent_match(
                    facet_value,
                    sku_row,
                    sku_text,
                    relevant_columns_for_facet,
                    knowledge_base,
                    match_type='facet',
                    embedding_cache=embedding_cache,
                    sku_embedding_cached=sku_embedding_cached,
                    sku_keywords_cached=sku_keywords_cached,
                    sku_text_data=sku_text_data,
                    column_text_overrides=facet_column_overrides,
                    semantic_threshold=semantic_threshold
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
    sku_keywords_cached: List[str] = None,
    sku_text_data: Optional[Dict] = None,
    column_text_overrides: Optional[Dict[str, str]] = None,
    semantic_threshold: Optional[float] = None,
    sku_text_override: Optional[str] = None
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
    normalized_target_words = target_normalized.split()
    significant_target_words = _extract_significant_words(normalized_target_words)
    
    if sku_text_override is not None:
        sku_text = sku_text_override
    
    sku_text_normalized_full = _normalize_value(sku_text) if sku_text else ''
    
    category_required_words = significant_target_words if match_type == 'category' and significant_target_words else []

    def has_significant_overlap(text, normalized_text=None):
        if match_type != 'category':
            return True
        if not significant_target_words:
            return True
        if text is None or (isinstance(text, float) and pd.isna(text)):
            return False
        if normalized_text is None:
            normalized_text = _normalize_value(str(text).lower())
        return any(word in normalized_text for word in significant_target_words)
    
    def category_words_met(normalized_text, words_source):
        if match_type != 'category':
            return None
        if not normalized_text:
            return False
        if category_required_words:
            return all(word in normalized_text for word in category_required_words)
        if not words_source:
            return False
        total_words = len(words_source)
        if total_words == 1:
            required = 1
        elif total_words == 2:
            required = 2
        else:
            required = max(2, int(math.ceil(total_words * 0.7)))
        words_found_count = sum(1 for word in words_source if word in normalized_text)
        return words_found_count >= required
    
    # Quick check: For multi-word phrases, do a simple substring check in full text first
    # This catches obvious matches like "anti mould paint" in product names
    # Use normalized values to handle hyphens and special characters (e.g., "Anti-Climb" matches "Anti Climb")
    normalized_phrase_tokens = normalized_target_words if normalized_target_words else target_lower.split()
    
    # For categories, check even shorter phrases and allow partial matches
    min_length = 6 if match_type == 'category' else 8
    if len(normalized_phrase_tokens) > 1 and len(target_normalized.replace(' ', '')) >= min_length:
        # Normalize values for comparison (handles hyphens, underscores, special chars)
        target_phrase_simple = _normalize_value(target_lower)
        sku_text_simple = sku_text_normalized_full
        
        # Simple substring match - if the phrase appears as-is, it's a match
        # This handles "anti-climb paint" matching "Anti Climb Paint"
        if target_phrase_simple in sku_text_simple:
            # For longer phrases, skip false positive check (they're usually legitimate)
            if _accept_positive_match(target_value, sku_text):
                return True
        
        # For categories, also check if key words appear as substring
        # E.g., "Low VOC Paint" should match "low voc" even if "paint" is missing
        if match_type == 'category' and len(normalized_phrase_tokens) >= 2:
            # Use normalized target words for checking
            # Check if at least 2 consecutive words appear together
            for i in range(len(normalized_phrase_tokens) - 1):
                two_word_phrase = f"{normalized_phrase_tokens[i]} {normalized_phrase_tokens[i+1]}"
                if two_word_phrase in sku_text_simple and _accept_positive_match(target_value, sku_text):
                    return True
    
    # Strategy 1: Exact match in ALL relevant columns (process every column, every cell, every character)
    # This ensures maximum accuracy by checking every column and every character
    column_text_cache = sku_text_data.get('column_texts', {}) if sku_text_data else {}
    
    for col in relevant_columns:
        if col not in sku_row.index:
            continue
        
        cache_entry = column_text_cache.get(col) if column_text_cache else None
        cached_multi_values = None
        
        # Process FULL cell value - every character, no truncation
        if column_text_overrides and col in column_text_overrides:
            cache_entry = None
            cell_value = column_text_overrides[col].strip()
            if not cell_value:
                continue
            cell_lower = cell_value.lower()
            cell_normalized = _normalize_value(cell_value)
        else:
            cell_raw = sku_row[col]
            if pd.isna(cell_raw):
                continue
            if cache_entry:
                cell_value = cache_entry.get('raw', '').strip()
                if not cell_value:
                    continue
                cell_lower = cache_entry.get('lower')
                if cell_lower is None:
                    cell_lower = cell_value.lower()
                cell_normalized = cache_entry.get('normalized')
                if cell_normalized is None:
                    cell_normalized = _normalize_value(cell_value)
                cached_multi_values = cache_entry.get('multi_values')
            else:
                cell_value = str(cell_raw).strip()
                if not cell_value:
                    continue
                cell_lower = cell_value.lower()
                cell_normalized = _normalize_value(cell_value)
        
        # Exact match (case-insensitive)
        if (target_lower == cell_lower or target_normalized == cell_normalized) and _accept_positive_match(target_value, cell_value):
            return True
        
        # Check for exact match within multi-value cells
        multi_value_candidates = cached_multi_values
        if multi_value_candidates is None:
            multi_value_candidates = _split_multi_value_cell(cell_value)
            if cache_entry is not None:
                cache_entry['multi_values'] = multi_value_candidates
        for candidate in multi_value_candidates:
            candidate_lower = candidate.lower()
            candidate_normalized = _normalize_value(candidate)
            if (target_lower == candidate_lower or target_normalized == candidate_normalized) and _accept_positive_match(target_value, cell_value):
                return True
        
        # For multi-word phrases, check if phrase appears in cell value
        target_words_for_cell = normalized_target_words if normalized_target_words else target_lower.split()
        if len(target_words_for_cell) > 1:
            if match_type == 'category':
                words_found = category_words_met(cell_normalized, target_words_for_cell)
            else:
                words_found = all(word in cell_normalized for word in target_words_for_cell)
            
            if words_found and match_type == 'category' and not has_significant_overlap(cell_value, cell_normalized):
                words_found = False
            
            if words_found:
                # Use normalized values for comparison (handles hyphens, underscores, special chars)
                # This ensures "Anti-Climb Paint" matches "Anti Climb Paint"
                target_phrase_normalized = _normalize_value(target_lower)
                cell_normalized = _normalize_value(cell_lower)
                
                # Strategy 1: Full phrase appears as substring (most lenient)
                # This handles "anti mould paint" matching "6 year anti mould paint 2.5l"
                # Also handles "anti-climb paint" matching "Anti Climb Paint"
                if target_phrase_normalized in cell_normalized and _accept_positive_match(target_value, cell_value):
                    return True
                
                # Strategy 2: Remove all spaces and check if phrase matches
                # This handles "antimouldpaint" vs "anti mould paint" variations
                # Also handles "anti-climb-paint" vs "antclimbpaint" etc.
                target_no_spaces = target_phrase_normalized.replace(' ', '')
                cell_no_spaces = cell_normalized.replace(' ', '')
                if target_no_spaces in cell_no_spaces and _accept_positive_match(target_value, cell_value):
                    return True
                
                # Strategy 3: Check if words appear in order and close together
                # Allow words to have other text between them (like "6 year" between words)
                # Use normalized target words to handle hyphens (e.g., "anti-climb" becomes ["anti", "climb"])
                # Create list of (position, word) tuples using normalized words
                raw_positions = [(cell_normalized.find(word), word) for word in target_words_for_cell]
                # Filter out -1 (not found)
                raw_positions = [(pos, word) for pos, word in raw_positions if pos >= 0]
                
                if match_type == 'category' and category_required_words:
                    word_positions = [(pos, word) for pos, word in raw_positions if word in category_required_words]
                    required_for_order = category_required_words
                    sufficient_positions = len(word_positions) >= len(required_for_order)
                else:
                    word_positions = raw_positions
                    required_for_order = target_words_for_cell
                    sufficient_positions = len(word_positions) >= len(required_for_order) if match_type == 'category' else len(word_positions) == len(required_for_order)
                
                if sufficient_positions:
                    # Sort by position
                    word_positions_sorted = sorted(word_positions, key=lambda x: x[0])
                    sorted_words = [word for pos, word in word_positions_sorted]
                    
                    # Check if words are in correct order and reasonably close (within 100 chars)
                    # For categories, allow partial matches
                    if match_type == 'category':
                        # Check if normalized words appear in order (allow partial matches)
                        target_indices = [required_for_order.index(word) for word in sorted_words if word in required_for_order]
                        words_in_order = (target_indices == sorted(target_indices)) if target_indices else False
                    else:
                        # For facets, require exact match
                        words_in_order = (sorted_words == required_for_order)
                    
                    if words_in_order:
                        first_pos = word_positions_sorted[0][0]
                        last_pos = word_positions_sorted[-1][0] + len(word_positions_sorted[-1][1])
                        if (last_pos - first_pos) < 100:
                            if (match_type != 'category' or has_significant_overlap(cell_value, cell_normalized)) and _accept_positive_match(target_value, cell_value):
                                return True
        
        # Word boundary matching (prevents substring matches for single words)
        if _word_boundary_match(target_lower, cell_lower) and _accept_positive_match(target_value, cell_value):
            return True
    
    # Strategy 2: Phrase/substring matching for multi-word targets (less strict)
    target_words = normalized_target_words if normalized_target_words else target_lower.split()
    if len(target_words) > 1:
        sku_text_normalized = sku_text_normalized_full
        if match_type == 'category':
            words_in_text = category_words_met(sku_text_normalized, target_words)
        else:
            words_in_text = all(word in sku_text_normalized for word in target_words)
        
        if words_in_text:
            # Use normalized values for comparison (handles hyphens, underscores, special chars)
            target_phrase = _normalize_value(target_lower)
            
            if match_type == 'category' and not has_significant_overlap(sku_text, sku_text_normalized):
                words_in_text = False
        
        if words_in_text:
            # Strategy 2a: Check if phrase appears as substring (most reliable)
            # This handles "anti mould paint" in "6 year anti mould paint 2.5l"
            if target_phrase in sku_text_normalized:
                # For multi-word phrases, be less aggressive with false positive checking
                # Only check if it's a very short word or known problematic pattern
                if len(target_phrase.replace(' ', '')) > 8:  # Longer phrases are usually legitimate
                    if (match_type != 'category' or has_significant_overlap(sku_text, sku_text_normalized)) and _accept_positive_match(target_value, sku_text):
                        return True
                elif not _is_likely_false_positive(target_value, sku_text, knowledge_base):
                    if (match_type != 'category' or has_significant_overlap(sku_text, sku_text_normalized)) and _accept_positive_match(target_value, sku_text):
                        return True
            
            # Strategy 2b: Check if words appear in order and reasonably close
            # This handles cases where words might be separated by other text
            # For categories, ensure required words appear in order; facets require all words
            raw_positions = []
            for word in target_words:
                pos = sku_text_normalized.find(word)
                if pos >= 0:
                    raw_positions.append((pos, word))
            
            if match_type == 'category' and category_required_words:
                word_positions = [(pos, word) for pos, word in raw_positions if word in category_required_words]
                required_for_order = category_required_words
                sufficient_positions = len(word_positions) >= len(required_for_order)
            else:
                word_positions = raw_positions
                required_for_order = target_words
                required_count = len(required_for_order) if match_type != 'category' else max(2, int(len(required_for_order) * 0.7))
                sufficient_positions = len(word_positions) >= required_count if match_type == 'category' else len(word_positions) == len(required_for_order)
            
            if sufficient_positions:
                # Check if words appear in order
                positions_sorted = sorted(word_positions, key=lambda x: x[0])
                sorted_words = [word for _, word in positions_sorted]
                
                # For categories, check if words appear in correct relative order (allow partial matches)
                # For facets, require exact order match
                words_in_order = False
                if match_type == 'category':
                    # For categories: check if the words that appear are in the same relative order
                    # E.g., if target is ["low", "voc", "paint"] and SKU has ["low", "voc"], that's valid
                    target_indices = [required_for_order.index(word) for word in sorted_words if word in required_for_order]
                    words_in_order = (target_indices == sorted(target_indices)) if target_indices else False
                else:
                    # For facets: require exact order match
                    words_in_order = (sorted_words == required_for_order)
                
                if words_in_order:
                    # For multi-word phrases, allow more distance between words (up to 100 chars)
                    first_pos = positions_sorted[0][0]
                    last_pos = positions_sorted[-1][0] + len(positions_sorted[-1][1])
                    if (last_pos - first_pos) < 100:
                        if len(target_phrase.replace(' ', '')) > 8:
                            if (match_type != 'category' or has_significant_overlap(sku_text, sku_text_normalized)) and _accept_positive_match(target_value, sku_text):
                                return True
                        elif not _is_likely_false_positive(target_value, sku_text, knowledge_base):
                            if (match_type != 'category' or has_significant_overlap(sku_text, sku_text_normalized)) and _accept_positive_match(target_value, sku_text):
                                return True
    
    # Strategy 3: Word boundary matching in full text
    if _word_boundary_match(target_lower, sku_text) and _accept_positive_match(target_value, sku_text):
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
                        sku_keywords_set = set(sku_keywords)
                        
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
                        
                        # Use lower threshold for categories (more lenient matching) unless overridden
                        base_threshold = 0.60 if match_type == 'category' else 0.65
                        similarity_threshold = semantic_threshold if semantic_threshold is not None else base_threshold
                        keyword_overlap_threshold = 0.5 if match_type == 'category' else 0.6  # More lenient for categories
                        
                        if similarity >= similarity_threshold:
                            keyword_hits = 0
                            required_hits = 0
                            if target_keywords:
                                required_hits = max(1, int(math.ceil(len(target_keywords) * keyword_overlap_threshold)))
                                if sku_keywords_set:
                                    keyword_hits = len(set(target_keywords) & sku_keywords_set)
                            if target_keywords and keyword_hits >= required_hits:
                                return True
                            if match_type == 'category' and has_significant_overlap(sku_text, sku_text_normalized_full):
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
                        
                        # Use lower threshold for categories (more lenient matching) unless overridden
                        base_threshold = 0.60 if match_type == 'category' else 0.65
                        similarity_threshold = semantic_threshold if semantic_threshold is not None else base_threshold
                        keyword_overlap_threshold = 0.4 if match_type == 'category' else 0.5  # More lenient for categories
                        
                        if similarity >= similarity_threshold:
                            cell_keywords = [token.lemma_.lower() for token in cell_doc if not token.is_stop and token.is_alpha]
                            cell_keywords_set = set(cell_keywords)
                            keyword_hits = 0
                            required_hits = 0
                            if target_keywords:
                                required_hits = max(1, int(math.ceil(len(target_keywords) * keyword_overlap_threshold)))
                                keyword_hits = len(set(target_keywords) & cell_keywords_set)
                            if target_keywords and keyword_hits >= required_hits:
                                return True
                            if match_type == 'category' and has_significant_overlap(cell_value, cell_normalized):
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
    sku_text_normalized = sku_text_normalized_full
    if target_normalized in sku_text_normalized:
        # For multi-word phrases longer than 8 characters, skip false positive check
        # (they're usually legitimate matches)
        if len(target_normalized.replace(' ', '')) > 8:
            if _accept_positive_match(target_value, sku_text):
                return True
        # Additional context check for shorter targets
        if _is_likely_false_positive(target_value, sku_text, knowledge_base):
            return False
        if _accept_positive_match(target_value, sku_text):
            return True
    
    # Strategy 6: For multi-word phrases, check if normalized phrase appears as substring
    # This handles variations in spacing/special characters
    if len(target_words) > 1:
        target_normalized_phrase = ' '.join([_normalize_value(word) for word in target_words])
        if target_normalized_phrase in sku_text_normalized:
            # Multi-word phrases are usually legitimate matches
            if len(target_normalized_phrase.replace(' ', '')) > 8:
                if _accept_positive_match(target_value, sku_text):
                    return True
            if not _is_likely_false_positive(target_value, sku_text, knowledge_base) and _accept_positive_match(target_value, sku_text):
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

