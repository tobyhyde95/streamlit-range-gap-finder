# seo_analyzer/stock_classifier.py
"""
Stock Classification Module (FR2).

Cross-references search queries against a product catalogue to classify
each query as either "Stocked" or "Not Stocked".

Target: >95% accuracy against live catalogue.

Matching strategy:
1. Exact match — query appears verbatim in product names (case-insensitive)
2. Token overlap — all significant tokens in the query appear in at least one
   product name (handles word-order and phrasing variations)
3. Fuzzy match — uses token-set ratio for partial/approximate matches

Only "Not Stocked" queries proceed to the clustering stage.
"""

import json
import os
import re

import pandas as pd
import numpy as np

try:
    from rapidfuzz import fuzz as rapidfuzz_fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

_config_path = os.path.join(os.path.dirname(__file__), "scoring_config.json")


def _load_stock_config():
    """Load stock matching config."""
    try:
        with open(_config_path, "r") as f:
            config = json.load(f)
        return config.get("stock_matching", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _normalise_text(text: str) -> str:
    """Lowercase, strip, remove excess whitespace and special characters."""
    if not isinstance(text, str):
        return ""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _tokenise(text: str) -> set:
    """Split normalised text into a set of tokens, excluding very short ones."""
    return {t for t in text.split() if len(t) > 1}


def load_product_catalogue(catalogue_path: str, product_name_col: str = None) -> pd.DataFrame:
    """
    Load the product catalogue CSV.

    Auto-detects the product name column if not specified.
    Returns a DataFrame with a normalised 'product_name_normalised' column.
    """
    from .data_loader import read_csv_with_encoding_fallback

    with open(catalogue_path, 'rb') as f:
        cat_df = read_csv_with_encoding_fallback(f)

    if cat_df is None or cat_df.empty:
        raise ValueError("Could not read the product catalogue CSV.")

    # Auto-detect product name column
    if product_name_col is None:
        candidates = ['product name', 'productname', 'product_name', 'name',
                       'title', 'product title', 'product', 'item', 'description',
                       'item name', 'sku name', 'product description']
        lower_cols = {c.lower().replace('_', ' '): c for c in cat_df.columns}
        for candidate in candidates:
            if candidate in lower_cols:
                product_name_col = lower_cols[candidate]
                break
        if product_name_col is None:
            # Default to first column
            product_name_col = cat_df.columns[0]
            print(f"Could not auto-detect product name column. Using first column: '{product_name_col}'")

    print(f"Using product catalogue column: '{product_name_col}' ({len(cat_df)} products)")

    cat_df = cat_df.dropna(subset=[product_name_col]).copy()
    cat_df['product_name_normalised'] = cat_df[product_name_col].apply(_normalise_text)
    cat_df['product_tokens'] = cat_df['product_name_normalised'].apply(_tokenise)
    cat_df['_original_product_col'] = product_name_col

    return cat_df


def classify_queries(
    queries_df: pd.DataFrame,
    keyword_col: str,
    catalogue_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Classify each query as 'Stocked' or 'Not Stocked'.

    Returns the input DataFrame with two new columns:
    - 'Stock Status': 'Stocked' or 'Not Stocked'
    - 'Matched Product': the matched product name (if stocked), else None

    Matching strategy (applied in order, first match wins):
    1. Exact substring match — query appears in product name or vice versa
    2. Token containment — all query tokens found in at least one product
    3. Fuzzy match (if rapidfuzz available) — token_set_ratio > threshold
    """
    config = _load_stock_config()
    fuzzy_threshold = config.get("fuzzy_threshold", 80)

    product_names = catalogue_df['product_name_normalised'].tolist()
    product_tokens_list = catalogue_df['product_tokens'].tolist()
    original_col = catalogue_df['_original_product_col'].iloc[0]
    original_names = catalogue_df[original_col].tolist()

    unique_keywords = queries_df[keyword_col].dropna().unique()
    classification = {}

    print(f"Classifying {len(unique_keywords)} unique queries against {len(product_names)} products...")

    for kw in unique_keywords:
        norm_kw = _normalise_text(str(kw))
        kw_tokens = _tokenise(norm_kw)

        matched = False
        matched_product = None

        if not kw_tokens:
            classification[kw] = ('Not Stocked', None)
            continue

        # Strategy 1: Exact substring match
        for i, pname in enumerate(product_names):
            if norm_kw in pname or pname in norm_kw:
                matched = True
                matched_product = original_names[i]
                break

        # Strategy 2: Token containment
        if not matched:
            for i, ptokens in enumerate(product_tokens_list):
                if kw_tokens.issubset(ptokens):
                    matched = True
                    matched_product = original_names[i]
                    break

        # Strategy 3: Fuzzy matching (rapidfuzz)
        if not matched and HAS_RAPIDFUZZ:
            best_score = 0
            best_idx = -1
            for i, pname in enumerate(product_names):
                score = rapidfuzz_fuzz.token_set_ratio(norm_kw, pname)
                if score > best_score:
                    best_score = score
                    best_idx = i
            if best_score >= fuzzy_threshold:
                matched = True
                matched_product = original_names[best_idx]

        classification[kw] = ('Stocked' if matched else 'Not Stocked', matched_product)

    # Map back to dataframe
    queries_df = queries_df.copy()
    queries_df['Stock Status'] = queries_df[keyword_col].map(
        lambda kw: classification.get(kw, ('Not Stocked', None))[0]
    )
    queries_df['Matched Product'] = queries_df[keyword_col].map(
        lambda kw: classification.get(kw, ('Not Stocked', None))[1]
    )

    n_stocked = (queries_df['Stock Status'] == 'Stocked').sum()
    n_not_stocked = (queries_df['Stock Status'] == 'Not Stocked').sum()
    print(f"Stock classification: {n_stocked} Stocked, {n_not_stocked} Not Stocked")

    return queries_df


def filter_not_stocked(df: pd.DataFrame) -> pd.DataFrame:
    """Return only rows classified as 'Not Stocked' for clustering."""
    if 'Stock Status' not in df.columns:
        return df
    return df[df['Stock Status'] == 'Not Stocked'].copy()
