import re
from collections import Counter, defaultdict
from urllib.parse import urlparse, parse_qs
from functools import lru_cache

import numpy as np
import pandas as pd
from nltk.stem import PorterStemmer
import spacy
import swifter
import subprocess
import sys

try:
    from .url_parser import URLParser
    from .synonym_discovery import SynonymDiscovery
except ImportError:
    from url_parser import URLParser
    from synonym_discovery import SynonymDiscovery


try:
    nlp = spacy.load("en_core_web_md")
except OSError:
    try:
        subprocess.run([sys.executable, "-m", "spacy", "download", "en_core_web_md"], check=True)
        nlp = spacy.load("en_core_web_md")
    except (subprocess.CalledProcessError, OSError):
        print("Failed to download or load SpaCy model. Please run 'python -m spacy download en_core_web_md' manually.")
        nlp = None


def _generate_enhanced_category_overhaul_matrix(
    df,
    internal_keyword_col,
    internal_position_col,
    internal_traffic_col,
    internal_url_col_name,
    onsite_df,
    internal_volume_col,
    topic_col='TopicID',
    enable_synonym_discovery=True
):
    """
    Enhanced version of category overhaul matrix using the new URL parser and synonym discovery.
    """
    if df.empty or internal_traffic_col not in df.columns:
        return {
            "matrix_report": [],
            "facet_potential_report": []
        }

    # Initialize the enhanced URL parser
    url_parser = URLParser()
    synonym_discovery = SynonymDiscovery() if enable_synonym_discovery else None
    
    stemmer = PorterStemmer()
    df_sorted = df.sort_values([internal_keyword_col, internal_position_col], ascending=[True, True])
    highest_ranking_df = df_sorted.drop_duplicates(subset=[internal_keyword_col], keep='first').copy()

    print("Learning category candidates from URL structures using enhanced parser...")
    
    # Extract categories using the new URL parser
    unique_urls = highest_ranking_df[internal_url_col_name].dropna().unique()
    
    # Use the enhanced category extraction
    highest_ranking_df['Original Category Mapping'] = highest_ranking_df[internal_url_col_name].apply(
        lambda url: url_parser.extract_category_from_url(url)
    )
    
    # Discover synonyms if enabled
    if synonym_discovery and enable_synonym_discovery:
        print("Discovering potential synonyms from URLs...")
        candidates = synonym_discovery.discover_synonyms_from_urls(unique_urls.tolist())
        if candidates:
            stored_ids = synonym_discovery.store_candidates(candidates)
            print(f"Discovered {len(candidates)} potential synonyms, stored {len(stored_ids)} in database")

    if onsite_df is not None and not onsite_df.empty:
        highest_ranking_df = pd.merge(highest_ranking_df, onsite_df, left_on=internal_keyword_col, right_on='keyword', how='left')
        highest_ranking_df.rename(columns={'searches': 'On-Site Searches'}, inplace=True)
        highest_ranking_df.drop(columns=['keyword'], inplace=True, errors='ignore')

    highest_ranking_df['On-Site Searches'] = highest_ranking_df.get('On-Site Searches', pd.Series(0, index=highest_ranking_df.index)).fillna(0).astype(int)

    @lru_cache(maxsize=None)
    def get_word_forms(word):
        word = str(word).lower()
        forms = {word}
        if word.endswith('s'):
            forms.add(word[:-1])
        else:
            forms.add(word + 's')
        forms.add(PorterStemmer().stem(word))
        return forms

    category_counts = highest_ranking_df['Original Category Mapping'].value_counts()
    category_stems = {}
    for cat in category_counts.index:
        if pd.isna(cat):
            continue
        stem = PorterStemmer().stem(str(cat).lower().replace(' ', ''))
        if stem not in category_stems:
            category_stems[stem] = []
        category_stems[stem].append(cat)

    category_normalization_map = {}
    for stem, cats in category_stems.items():
        canonical_cat = max(cats, key=lambda c: category_counts[c])
        for cat in cats:
            category_normalization_map[cat] = canonical_cat

    highest_ranking_df['Category Mapping'] = highest_ranking_df['Original Category Mapping'].map(category_normalization_map)

    def dynamic_decompound_and_refine(df, category_col, canonical_categories_set):
        if nlp is None:
            df['Derived Facets'] = None
            df['Decompounded Type'] = None
            return df

        unique_original_cats = df[df[category_col].notna()][category_col].unique()
        decompound_map = {}
        splittable_attributes = {'wheeled', 'rolling', 'storage', 'systems', 'cordless', 'electric'}

        for cat_str in unique_original_cats:
            if pd.isna(cat_str):
                continue
            doc = nlp(cat_str.lower())
            root = next((token for token in doc if token.head == token), None)
            potential_cat_word = root.lemma_ if root else None
            final_category = None

            if potential_cat_word and canonical_categories_set:
                best_match, best_match_sim = None, 0.0
                for canon_cat in canonical_categories_set:
                    if pd.isna(canon_cat):
                        continue
                    sim = nlp(potential_cat_word).similarity(nlp(canon_cat.lower()))
                    if sim > best_match_sim:
                        best_match, best_match_sim = canon_cat, sim
                if best_match and best_match_sim > 0.7:
                    final_category = best_match
                    other_words = [token.text for token in doc if token.lemma_ != potential_cat_word and token.is_alpha]
                    derived_facets_set = {word.title() for word in other_words if word in splittable_attributes}
                    type_facet_words = [word for word in other_words if word not in splittable_attributes]
                    type_facet = ' '.join(type_facet_words).title() if type_facet_words else None
                    derived_facets = ', '.join(sorted(derived_facets_set)) if derived_facets_set else None
                else:
                    final_category = cat_str
                    derived_facets = None
                    type_facet = None
            else:
                final_category = cat_str
                derived_facets = None
                type_facet = None

            if type_facet and final_category and (final_category.startswith(type_facet) or type_facet.startswith(final_category)):
                type_facet = None

            decompound_map[cat_str] = (final_category, derived_facets, type_facet)

        refined_data = df[category_col].map(decompound_map).apply(pd.Series)
        refined_data.columns = ['Refined Category', 'Derived Facets', 'Decompounded Type']

        df['Category Mapping'] = np.where(refined_data['Refined Category'].notna(), refined_data['Refined Category'], df['Category Mapping'])
        df['Derived Facets'] = refined_data['Derived Facets']
        df['Decompounded Type'] = refined_data['Decompounded Type']
        return df

    # REFACTORING: Task 1 - Disable semantic category overwrites
    # This semantic clustering was causing incorrect merging of distinct categories
    # (e.g., 'wood paint' incorrectly merging into 'cladding')
    # all_canonical_categories = set(highest_ranking_df['Category Mapping'].dropna().unique())
    # highest_ranking_df = dynamic_decompound_and_refine(highest_ranking_df, 'Category Mapping', all_canonical_categories)
    
    # Instead, preserve the URL-based category mapping and only extract supplementary features
    highest_ranking_df['Derived Facets'] = None
    highest_ranking_df['Decompounded Type'] = None

    # REFACTORING: Task 2 - Remove traffic-based category reclassification
    # This logic was forcing niche products into incorrect high-volume categories
    # (e.g., "damp paint" being forced into "gloss" category)
    # The URL-based category mapping should be the definitive source of truth
    
    # Ensure traffic column is numeric for downstream processing
    if not highest_ranking_df.empty and internal_traffic_col in highest_ranking_df.columns:
        highest_ranking_df[internal_traffic_col] = pd.to_numeric(highest_ranking_df[internal_traffic_col], errors='coerce').fillna(0)

    def clean_facet_value(value):
        if pd.isnull(value):
            return None
        s = str(value)
        s = s.replace('_', ' ').replace('-', ' ')
        s = s.replace(' and ', ' & ')
        s = re.sub(r'[^\w\s&]', '', s)
        return ' '.join(s.split()).title()

    def extract_url_facets(url):
        try:
            # Use the enhanced facet normalization
            raw_facets = parse_qs(urlparse(str(url)).query)
            normalized_facets = {}
            for key, values in raw_facets.items():
                if values:
                    normalized_key = url_parser.normalize_facet_key(key)
                    normalized_facets[normalized_key] = clean_facet_value(values[0])
            return normalized_facets
        except Exception:
            return {}

    url_facets_list = highest_ranking_df[internal_url_col_name].apply(extract_url_facets).tolist()
    explicit_facets_df = pd.DataFrame(url_facets_list, index=highest_ranking_df.index)

    noise_cols = [
        'gclid', 'gclsrc', 'msclkid', 'mkwid', 'pkw', 'pcrid', 'pmt', 'fi', 'page',
        'sort_by', 'q', 'redirect', 'utm_source', 'utm_medium', 'utm_campaign',
        'utm_term', 'utm_content'
    ]
    cols_to_drop = [col for col in explicit_facets_df.columns if col.lower().replace(' ', '_') in noise_cols or col.lower().startswith('utm')]
    explicit_facets_df.drop(columns=cols_to_drop, inplace=True)

    knowledge_base = {col: set(explicit_facets_df[col].dropna().unique()) for col in explicit_facets_df.columns}
    facet_col_map = {key: key.title() for key in explicit_facets_df.columns}
    explicit_facets_df = explicit_facets_df.rename(columns=facet_col_map)

    if explicit_facets_df.columns.has_duplicates:
        explicit_facets_df = explicit_facets_df.groupby(level=0, axis=1).apply(lambda group: group.ffill(axis=1).bfill(axis=1).iloc[:, 0])

    # CRITICAL FIX: Check for column name collisions with existing DataFrame columns
    # If a facet column name already exists in the main DataFrame, rename the facet column
    # to avoid losing facet data during concatenation
    existing_cols = set(highest_ranking_df.columns)
    facet_rename_map = {}
    for col in explicit_facets_df.columns:
        if col in existing_cols:
            # Rename facet column to avoid collision
            # Example: "Volume" -> "Product Volume" if "Volume" already exists (search volume from Semrush)
            new_col_name = f"Product {col}" if col in ['Volume', 'Size', 'Weight', 'Capacity'] else f"{col} Facet"
            print(f"⚠️  Column collision detected: '{col}' already exists in data. Renaming facet column to '{new_col_name}'")
            facet_rename_map[col] = new_col_name
    
    if facet_rename_map:
        explicit_facets_df = explicit_facets_df.rename(columns=facet_rename_map)

    highest_ranking_df = pd.concat([highest_ranking_df, explicit_facets_df], axis=1)
    if highest_ranking_df.columns.has_duplicates:
        print(f"⚠️  Warning: Duplicate columns detected after concatenation: {highest_ranking_df.columns[highest_ranking_df.columns.duplicated()].tolist()}")
        highest_ranking_df = highest_ranking_df.groupby(level=0, axis=1).apply(lambda group: group.ffill(axis=1).bfill(axis=1).iloc[:, 0])

    # Continue with the rest of the analysis...
    # (This is a simplified version - the full implementation would continue with the existing logic)
    
    return {
        "matrix_report": [],  # Placeholder - would contain the actual matrix report
        "facet_potential_report": []  # Placeholder - would contain the actual facet report
    }
