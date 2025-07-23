# seo_analyzer/services.py
import pandas as pd
import json
import numpy as np
from . import utils
from . import analysis
from sklearn.preprocessing import MinMaxScaler
from urllib.parse import urlparse, parse_qs
import re
from collections import Counter, defaultdict
import os
from nltk.stem import PorterStemmer
import spacy
import swifter
import subprocess
import sys

# Load the SpaCy model, and download it if it's missing
try:
    nlp = spacy.load("en_core_web_md")
except OSError:
    print("Spacy model 'en_core_web_md' not found. Downloading now...")
    try:
        subprocess.run([sys.executable, "-m", "spacy", "download", "en_core_web_md"], check=True)
        nlp = spacy.load("en_core_web_md")
    except (subprocess.CalledProcessError, OSError):
        print("Failed to download or load SpaCy model. Please run 'python -m spacy download en_core_web_md' manually.")
        nlp = None


def _classify_intent(keyword):
    """A lean, rules-based function to classify keyword intent."""
    kw = str(keyword).lower()
    transactional_triggers = ['buy', 'price', 'cost', 'sale', 'discount', 'deal']
    if any(trigger in kw for trigger in transactional_triggers):
        return 'Transactional'
    informational_triggers = ['what', 'how', 'why', 'best', 'review', 'vs', 'compare', 'guide']
    if any(trigger in kw for trigger in informational_triggers):
        return 'Informational'
    return 'Commercial'

def _calculate_keyword_market_share(df, keyword_col, source_col, traffic_col):
    """Calculates estimated traffic share per individual keyword."""
    if traffic_col not in df.columns or df[traffic_col].isnull().all():
        return []

    df_filtered = df.dropna(subset=[keyword_col, source_col, traffic_col])
    
    traffic_pivot = df_filtered.pivot_table(index=keyword_col, columns=source_col, values=traffic_col, fill_value=0)
    traffic_pivot['Total Monthly Google Traffic'] = traffic_pivot.sum(axis=1)
    
    non_zero_traffic_mask = traffic_pivot['Total Monthly Google Traffic'] > 0
    
    all_sources = df_filtered[source_col].unique()
    for source in all_sources:
        if source in traffic_pivot.columns:
            share = np.where(
                non_zero_traffic_mask,
                (traffic_pivot[source] / traffic_pivot['Total Monthly Google Traffic']) * 100,
                0
            )
            traffic_pivot[source] = list(zip(share, traffic_pivot[source]))

    traffic_pivot.reset_index(inplace=True)
    traffic_pivot.rename(columns={keyword_col: 'Keyword'}, inplace=True)
    
    traffic_pivot.replace({np.nan: None}, inplace=True)
    return traffic_pivot.sort_values('Total Monthly Google Traffic', ascending=False).to_dict(orient='records')


def _calculate_group_market_share(df, keyword_group_col, source_col, traffic_col):
    """Calculates estimated traffic share per keyword group."""
    if traffic_col not in df.columns or df[traffic_col].isnull().all():
        return pd.DataFrame()
    
    df_filtered = df.dropna(subset=[keyword_group_col, source_col, traffic_col])
    market_share = df_filtered.groupby([keyword_group_col, source_col])[traffic_col].sum().unstack(fill_value=0)
    total_traffic = market_share.sum(axis=1)
    
    market_share_pct = market_share.copy()
    for col in market_share.columns:
        share = (market_share[col] / total_traffic).where(total_traffic > 0, 0) * 100
        market_share_pct[col] = list(zip(share, market_share[col]))
        
    market_share_pct['Total Monthly Google Traffic'] = total_traffic
    market_share_pct.reset_index(inplace=True)
    return market_share_pct.sort_values('Total Monthly Google Traffic', ascending=False)

def _generate_category_overhaul_matrix(df, internal_keyword_col, internal_position_col, internal_traffic_col, internal_url_col_name, onsite_df, internal_volume_col):
    """
    Generates a matrix of categories and facets using a "learn and classify" model.
    NOW MODIFIED to return both the detailed matrix and a high-level facet potential report.
    """
    if df.empty or internal_traffic_col not in df.columns:
        return {
            "matrix_report": [],
            "facet_potential_report": []
        }

    stemmer = PorterStemmer()
    df_sorted = df.sort_values([internal_keyword_col, internal_position_col], ascending=[True, True])
    highest_ranking_df = df_sorted.drop_duplicates(subset=[internal_keyword_col], keep='first').copy()

    # --- DYNAMIC CATEGORY LEARNING (PUREST CANDIDATE ALGORITHM) ---
    print("Learning category candidates from URL structures...")
    
    all_segments = []
    unique_urls = highest_ranking_df[internal_url_col_name].dropna().unique()
    for url in unique_urls:
        try:
            path_segments = [
                s.replace('-', ' ').replace('_', ' ') 
                for s in urlparse(str(url)).path.lower().strip('/').split('/') 
                # Stricter filter to ignore segments that look like IDs
                if re.search(r'[a-zA-Z]', s) and len(s) > 3 and not re.search(r'\d', s)
            ]
            all_segments.extend(path_segments)
        except Exception:
            continue

    segment_freq = Counter(all_segments)
    min_freq = max(2, int(len(unique_urls) * 0.01)) 
    strong_candidates = {segment for segment, freq in segment_freq.items() if freq >= min_freq}
    print(f"Found {len(strong_candidates)} strong candidates with min freq {min_freq}.")

    def find_best_category(url, candidates):
        """
        Finds the best category for a URL by selecting the right-most, purely alphabetic strong candidate.
        """
        try:
            path_segments = [
                s.replace('-', ' ').replace('_', ' ') 
                for s in urlparse(str(url)).path.lower().strip('/').split('/')
            ]
            
            valid_matches = [segment for segment in path_segments if segment in candidates]
            
            if not valid_matches:
                return None
            
            best_match = valid_matches[-1]
            return best_match.title()

        except Exception:
            return None

    if onsite_df is not None and not onsite_df.empty:
        highest_ranking_df = pd.merge(highest_ranking_df, onsite_df, left_on=internal_keyword_col, right_on='keyword', how='left')
        highest_ranking_df.rename(columns={'searches': 'On-Site Searches'}, inplace=True)
        highest_ranking_df.drop(columns=['keyword'], inplace=True, errors='ignore')
    
    highest_ranking_df['On-Site Searches'] = highest_ranking_df.get('On-Site Searches', pd.Series(0, index=highest_ranking_df.index)).fillna(0).astype(int)

    highest_ranking_df['Original Category Mapping'] = highest_ranking_df[internal_url_col_name].apply(find_best_category, candidates=strong_candidates)
    
    def get_word_forms(word):
        word = str(word).lower()
        forms = {word}
        if word.endswith('s'):
            forms.add(word[:-1])
        else:
            forms.add(word + 's')
        return forms
        
    category_counts = highest_ranking_df['Original Category Mapping'].value_counts()
    category_stems = {}
    for cat in category_counts.index:
        stem = stemmer.stem(str(cat).lower().replace(' ', ''))
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
            doc = nlp(cat_str.lower())
            root = next((token for token in doc if token.head == token), None)
            potential_cat_word = root.lemma_ if root else None
            final_category = None 

            if potential_cat_word and canonical_categories_set:
                best_match, best_match_sim = None, 0.0
                for canon_cat in canonical_categories_set:
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

    all_canonical_categories = set(highest_ranking_df['Category Mapping'].dropna().unique())
    highest_ranking_df = dynamic_decompound_and_refine(highest_ranking_df, 'Category Mapping', all_canonical_categories)

    if not highest_ranking_df.empty and internal_traffic_col in highest_ranking_df.columns:
        highest_ranking_df[internal_traffic_col] = pd.to_numeric(highest_ranking_df[internal_traffic_col], errors='coerce').fillna(0)
        category_traffic = highest_ranking_df.groupby('Category Mapping')[internal_traffic_col].sum()
        total_traffic_sum = category_traffic.sum()
        if total_traffic_sum > 0:
            strong_categories_from_traffic = set(category_traffic[category_traffic / total_traffic_sum > 0.005].index)
            strong_categories_from_traffic -= {'Tools', 'Hand Tools', 'Power Tools'} 

            generic_categories_to_reclassify = {'Tools', 'Hand Tools', 'Power Tools'}

            def reclassify_row(row):
                current_cat = row['Category Mapping']
                if current_cat in generic_categories_to_reclassify:
                    try:
                        url_path = urlparse(str(row[internal_url_col_name])).path.lower().strip('/')
                        if url_path == current_cat.lower().replace(' ', '-'):
                             return current_cat 
                    except:
                        pass

                    kw_tokens = set(str(row[internal_keyword_col]).lower().split())
                    for strong_cat in strong_categories_from_traffic:
                        strong_cat_forms = get_word_forms(strong_cat.lower())
                        if not kw_tokens.isdisjoint(strong_cat_forms):
                            return strong_cat
                return current_cat
            highest_ranking_df['Category Mapping'] = highest_ranking_df.swifter.apply(reclassify_row, axis=1)

    def clean_facet_value(value):
        if pd.isnull(value): return None
        s = str(value)
        s = s.replace('_', ' ').replace('-', ' ')
        s = s.replace(' and ', ' & ')
        s = re.sub(r'[^\w\s&]', '', s)
        return ' '.join(s.split()).title()

    def extract_url_facets(url):
        try:
            return {k.lower(): clean_facet_value(v[0]) for k, v in parse_qs(urlparse(str(url)).query).items() if v}
        except: return {}
        
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
    explicit_facets_df.rename(columns=facet_col_map, inplace=True)

    if explicit_facets_df.columns.has_duplicates:
        explicit_facets_df = explicit_facets_df.groupby(level=0, axis=1).apply(lambda group: group.ffill(axis=1).bfill(axis=1).iloc[:, 0])

    highest_ranking_df = pd.concat([highest_ranking_df, explicit_facets_df], axis=1)

    # --- FINAL FIX: Catch any duplicates created by the concat operation ---
    if highest_ranking_df.columns.has_duplicates:
        highest_ranking_df = highest_ranking_df.groupby(level=0, axis=1).apply(lambda group: group.ffill(axis=1).bfill(axis=1).iloc[:, 0])
    
    potential_facet_cols = [
        col for col in highest_ranking_df.columns
        if highest_ranking_df[col].dtype == 'object' and col not in [
            'Category Mapping', 'Original Category Mapping', 'Derived Facets',
            'Decompounded Type', internal_keyword_col, internal_url_col_name, 'Source',
            'Keyword Group'
        ]
    ]

    all_values = highest_ranking_df[potential_facet_cols].unstack().dropna().astype(str).str.title().value_counts()
    key_values = all_values[(all_values > 1) & (all_values.index.str.len() > 3) & (all_values.index.str.isalpha())].index
    
    value_to_home_column = {}
    for value in key_values:
        col_counts = {}
        for col in potential_facet_cols:
            count = highest_ranking_df[col].str.contains(value, na=False, case=False).sum()
            if count > 0:
                col_counts[col] = count
        if col_counts:
            home_column = max(col_counts, key=col_counts.get)
            value_to_home_column[value] = home_column

    for value, home_col in value_to_home_column.items():
        for source_col in potential_facet_cols:
            if source_col == home_col:
                continue
            
            mask = highest_ranking_df[source_col].str.contains(value, na=False, case=False)
            if mask.any():
                existing_vals = highest_ranking_df.loc[mask, home_col].fillna('')
                new_vals = existing_vals.apply(lambda x: ' | '.join(sorted(set(x.split(' | ') + [value]))).strip(' | '))
                highest_ranking_df.loc[mask, home_col] = new_vals
                highest_ranking_df.loc[mask, source_col] = highest_ranking_df.loc[mask, source_col].str.replace(value, '', case=False, regex=False).str.replace(r'\s*\|\s*\|*\s*', '|', regex=True).str.strip(' |')

    highest_ranking_df.replace('', np.nan, inplace=True)

    def jaccard_similarity(set1, set2):
        if not set1 and not set2: return 0.0
        set1_split = {item.strip() for val in set1 for item in str(val).split(' | ')}
        set2_split = {item.strip() for val in set2 for item in str(val).split(' | ')}
        intersection = len(set1_split.intersection(set2_split))
        union = len(set1_split.union(set2_split))
        return intersection / union if union > 0 else 0.0

    temp_cols = list(highest_ranking_df.columns)
    merged_cols_map = {}
    cols_to_process = [col for col in temp_cols if col not in ['Category Mapping', 'Original Category Mapping', 'Derived Facets', 'Decompounded Type', internal_keyword_col, internal_url_col_name]]
    
    for i in range(len(cols_to_process)):
        for j in range(i + 1, len(cols_to_process)):
            col1, col2 = cols_to_process[i], cols_to_process[j]
            if col1 in highest_ranking_df and col2 in highest_ranking_df:
                set1 = set(highest_ranking_df[col1].dropna().unique())
                set2 = set(highest_ranking_df[col2].dropna().unique())
                
                sim_score = jaccard_similarity(set1, set2)
                if 0.6 <= sim_score < 0.8 and len(set1) > 0 and len(set2) > 0:
                    print(f"INFO: Near miss for column consolidation: '{col1}' and '{col2}' (Jaccard Similarity: {sim_score:.2f})")
                if len(set1) > 0 and len(set2) > 0 and sim_score > 0.8:
                    canonical = col1 if len(col1) <= len(col2) else col2
                    to_merge = col2 if canonical == col1 else col1
                    if canonical not in merged_cols_map:
                         merged_cols_map[canonical] = []
                    merged_cols_map[canonical].append(to_merge)
    
    for canonical, to_merge_list in merged_cols_map.items():
        for col in to_merge_list:
            if col in highest_ranking_df.columns and canonical in highest_ranking_df.columns:
                highest_ranking_df[canonical].fillna(highest_ranking_df[col], inplace=True)
                highest_ranking_df.drop(columns=[col], inplace=True, errors='ignore')

    all_facet_cols = {col for col in potential_facet_cols if col in highest_ranking_df.columns} | {'Derived Facets', 'Discovered Facets'}

    def is_redundant(category, facet_val):
        if pd.isnull(category) or pd.isnull(facet_val): return False
        cat_str = str(category).lower().replace('-', ' ')
        facet_str = str(facet_val).lower().replace('-', ' ')
        cat_tokens = {item for word in cat_str.split() for item in get_word_forms(word)}
        facet_tokens = set(facet_str.split())
        
        cat_variations = category_stems.get(stemmer.stem(str(category).lower().replace(' ', '')), [])
        for variation in cat_variations:
            cat_tokens.update(get_word_forms(variation))
            
        return facet_tokens.issubset(cat_tokens)

    for col in all_facet_cols:
        if col in highest_ranking_df.columns and col != 'Category Mapping':
             highest_ranking_df[col] = highest_ranking_df.apply(
                lambda row: None if is_redundant(row['Category Mapping'], row[col]) else row[col],
                axis=1
            )
            
    UNIVERSAL_IGNORE_TOKENS = {
        'for', 'and', 'the', 'with', 'in', 'a', 'of', 'for', 'sale', 'best',
        'cheap', 'deals', 'price', 'cost', 'vs', 'reviews', 'guide', 'near',
        'buy', 'offers', 'clearance', 'store', 'shop', 'b&q', 'asda', 'tesco',
        'halfords', 'middlesbrough', 'sales'
    }

    def discover_remaining_facets(row):
        if nlp is None:
            return None

        ignore_tokens = UNIVERSAL_IGNORE_TOKENS.copy()

        if pd.notnull(row['Category Mapping']):
            for cat_word in str(row['Category Mapping']).lower().split():
                ignore_tokens.update(get_word_forms(cat_word))

        synonym_map = {'tool boxes': {'toolbox', 'toolboxes'}, 'multi-tools': {'multitool'}, 'lawnmowers': {'lawnmower'}}
        cat_lower = str(row.get('Category Mapping', '')).lower()
        if cat_lower in synonym_map:
            ignore_tokens.update(synonym_map[cat_lower])
        
        try:
            path_segments = urlparse(str(row[internal_url_col_name])).path.lower().split('/')
            for segment in path_segments:
                ignore_tokens.update(segment.replace('-', ' ').replace('_', ' ').split())
        except:
            pass
        
        assigned_facet_values = set()
        facet_cols = list(all_facet_cols - {'Discovered Facets'})
        for col in facet_cols:
             if col in row and pd.notnull(row[col]):
                values = str(row[col]).split(' | ')
                for val in values:
                    assigned_facet_values.update(val.strip().lower().split())
        ignore_tokens.update(assigned_facet_values)
        
        doc = nlp(str(row[internal_keyword_col]).lower())
        
        potential_facets = {token.lemma_ for token in doc if token.pos_ in ['NOUN', 'PROPN', 'ADJ']}
        
        discovered = potential_facets - ignore_tokens
        
        low_value_terms = {'set', 'kit', 'pack', 'box', 'gun', 'type', 'accessories', 'parts', 'tool', 'bits'}
        discovered = discovered - low_value_terms
        
        discovered_clean = [token.title() for token in discovered if len(token) > 2 and not token.isdigit()]
        return ', '.join(sorted(discovered_clean)) if discovered_clean else None
        
    highest_ranking_df['Discovered Facets'] = highest_ranking_df.swifter.apply(discover_remaining_facets, axis=1)

    highest_ranking_df.dropna(axis=1, how='all', inplace=True)
    
    grouping_cols = ['Category Mapping'] + sorted([col for col in all_facet_cols if col in highest_ranking_df.columns])
    
    for col in grouping_cols:
        if col not in highest_ranking_df.columns:
            highest_ranking_df[col] = None
    
    highest_ranking_df[grouping_cols] = highest_ranking_df[grouping_cols].fillna('')
    highest_ranking_df[internal_traffic_col] = pd.to_numeric(highest_ranking_df[internal_traffic_col], errors='coerce').fillna(0)

    agg_dict = {
        internal_traffic_col: 'sum'
    }
    if 'On-Site Searches' in highest_ranking_df.columns:
        agg_dict['On-Site Searches'] = 'sum'
    if internal_volume_col and internal_volume_col in highest_ranking_df.columns:
        highest_ranking_df[internal_volume_col] = pd.to_numeric(highest_ranking_df[internal_volume_col], errors='coerce').fillna(0)
        agg_dict[internal_volume_col] = 'sum'

    filtered_agg_dict = {k: v for k, v in agg_dict.items() if k not in grouping_cols}

    matrix_df = highest_ranking_df.groupby(grouping_cols, as_index=False).agg(filtered_agg_dict)

    def aggregate_keyword_details(group):
        sorted_group = group.sort_values(by=internal_traffic_col, ascending=False)
        details = []
        for _, row in sorted_group.iterrows():
            detail_row = {
                'Keyword': row[internal_keyword_col],
                'Monthly Google Searches': row.get(internal_volume_col, 0),
                'On-Site Searches': row.get('On-Site Searches', 0),
                'Monthly Organic Traffic': round(row.get(internal_traffic_col, 0)),
                'Top Ranking Competitor': row.get('Source', 'N/A'),
                'Rank': row.get(internal_position_col, 'N/A'),
                'URL': row.get(internal_url_col_name, '#')
            }
            details.append(detail_row)
        return details

    keyword_details_agg = highest_ranking_df.groupby(grouping_cols).apply(aggregate_keyword_details, include_groups=False).rename('KeywordDetails').reset_index()
    matrix_df = pd.merge(matrix_df, keyword_details_agg, on=grouping_cols, how='left')

    matrix_df.rename(columns={
        internal_traffic_col: 'Monthly Organic Traffic',
        internal_volume_col: 'Total Monthly Google Searches',
        'On-Site Searches': 'Total On-Site Searches'
    }, inplace=True)
    
    cols_to_check_for_empty = [col for col in grouping_cols if col != 'Category Mapping' and col in matrix_df.columns]

    matrix_df.sort_values('Monthly Organic Traffic', ascending=False, inplace=True)
    
    # Convert metric columns to integers for clean display
    for col in ['Monthly Organic Traffic', 'Total Monthly Google Searches', 'Total On-Site Searches']:
        if col in matrix_df.columns:
            matrix_df[col] = matrix_df[col].astype(int)

    final_cols = [col for col in grouping_cols if col in matrix_df.columns] + ['Monthly Organic Traffic']
    if 'Total Monthly Google Searches' in matrix_df.columns:
        final_cols.append('Total Monthly Google Searches')
    if 'Total On-Site Searches' in matrix_df.columns:
        final_cols.append('Total On-Site Searches')
    
    matrix_df = matrix_df[final_cols + ['KeywordDetails']]

    # --- START: NEW FACET POTENTIAL ANALYSIS LOGIC ---
    facet_potential_report_raw = []
    # Identify all columns that are acting as facets
    facet_cols = [col for col in grouping_cols if col != 'Category Mapping' and col in highest_ranking_df.columns]

    if facet_cols:
        id_vars = ['Category Mapping', internal_keyword_col]
        metric_cols = []
        if internal_traffic_col and internal_traffic_col in highest_ranking_df.columns:
            id_vars.append(internal_traffic_col)
            metric_cols.append(internal_traffic_col)
        if internal_volume_col and internal_volume_col in highest_ranking_df.columns:
            id_vars.append(internal_volume_col)
            metric_cols.append(internal_volume_col)
        if 'On-Site Searches' in highest_ranking_df.columns:
            id_vars.append('On-Site Searches')
            metric_cols.append('On-Site Searches')

        # Use melt to transform the wide facet columns into a long format
        melted_df = highest_ranking_df.melt(
            id_vars=id_vars,
            value_vars=facet_cols,
            var_name='Facet Type',
            value_name='Facet Value'
        )

        # We only care about rows where a facet value actually existed
        melted_df.dropna(subset=['Facet Value'], inplace=True)
        melted_df = melted_df[melted_df['Facet Value'] != '']
        
        if not melted_df.empty:
            # --- START: CORRECTED AGGREGATION FOR NESTING ---

            # 1. Create the detailed value-level report first
            value_agg_ops = {col: 'sum' for col in metric_cols}
            value_agg_ops[internal_keyword_col] = pd.Series.nunique
            
            value_level_df = melted_df.groupby(['Category Mapping', 'Facet Type', 'Facet Value'], as_index=False).agg(value_agg_ops)
            
            value_level_df.rename(columns={
                internal_traffic_col: 'Monthly Organic Traffic',
                internal_volume_col: 'Total Monthly Google Searches',
                'On-Site Searches': 'Total On-Site Searches',
                internal_keyword_col: 'Keyword Count'
            }, inplace=True, errors='ignore')

            # 2. Now, create the parent-level report by aggregating the value-level data
            parent_cols = ['Category Mapping', 'Facet Type']
            parent_agg_cols = [col for col in ['Monthly Organic Traffic', 'Total Monthly Google Searches', 'Total On-Site Searches', 'Keyword Count'] if col in value_level_df.columns]
            
            parent_level_df = value_level_df.groupby(parent_cols, as_index=False)[parent_agg_cols].sum()

            # 3. Calculate the Facet Value Score on the aggregated parent-level data
            master_weights = {
                'Monthly Organic Traffic': 0.34,
                'Total Monthly Google Searches': 0.33,
                'Total On-Site Searches': 0.33
            }
            available_cols = [col for col in master_weights.keys() if col in parent_level_df.columns and not parent_level_df[col].isnull().all()]

            if available_cols and len(available_cols) > 0:
                # Re-balance weights based on available data
                total_weight_available = sum(master_weights[col] for col in available_cols)
                dynamic_weights = {col: master_weights[col] / total_weight_available for col in available_cols}
                
                # Normalize only the available columns
                scaler = MinMaxScaler()
                normalized_data = scaler.fit_transform(parent_level_df[available_cols])
                normalized_df = pd.DataFrame(normalized_data, columns=available_cols, index=parent_level_df.index)

                # Calculate score using the dynamically balanced weights
                score = pd.Series(0, index=parent_level_df.index)
                for col, weight in dynamic_weights.items():
                    score += normalized_df[col] * weight
                
                parent_level_df['Facet Value Score'] = (score * 100).round(0)

            # 4. EFFICIENTLY gather nested details and merge back to the parent report
            details_series = value_level_df.groupby(parent_cols).apply(
                lambda g: g.sort_values('Monthly Organic Traffic', ascending=False).to_dict('records')
            )
            details_series.name = 'FacetValueDetails'
            
            final_report_df = parent_level_df.set_index(parent_cols).join(details_series).reset_index()
            
            # --- END: CORRECTED AGGREGATION FOR NESTING ---
            
            facet_potential_report_raw = final_report_df.to_dict(orient='records')

    # --- END: NEW FACET POTENTIAL ANALYSIS LOGIC ---
    
    matrix_df.replace({pd.NA: None, np.nan: None, '': None}, inplace=True)

    # MODIFIED: Return a dictionary containing both reports
    return {
        "matrix_report": matrix_df.to_dict(orient='records'),
        "facet_potential_report": facet_potential_report_raw
    }


def run_full_analysis(our_file_path, competitor_file_paths, onsite_file_path, options_str, progress_reporter=None):
    
    COLS_TO_EXCLUDE_AT_SOURCE = {
        'countrycode', 'location', 'serpfeatures', 'kd', 'cpc', 'paidtraffic',
        'currenturlinside', 'updated', 'branded', 'local', 'navigational',
        'informational', 'commercial', 'transactional'
    }

    def create_topic_report(df_for_topic_report_input, full_onsite_df):
        if df_for_topic_report_input.empty: return pd.DataFrame(), {}
        df_for_topic_report_cleaned = df_for_topic_report_input.dropna(subset=[internal_keyword_col]).copy()
        if df_for_topic_report_cleaned.empty: return pd.DataFrame(), {}
        
        if has_onsite_data and full_onsite_df is not None:
            temp_unique_keywords_df = df_for_topic_report_cleaned.drop_duplicates(subset=[internal_keyword_col]).copy()
            temp_unique_keywords_df['lower_keyword'] = temp_unique_keywords_df[internal_keyword_col].str.lower()
            temp_unique_keywords_df = pd.merge(temp_unique_keywords_df, full_onsite_df, left_on='lower_keyword', right_on='keyword', how='left')
            onsite_searches_series = temp_unique_keywords_df.set_index(internal_keyword_col)['searches']
            df_for_topic_report_cleaned['On-Site Searches'] = df_for_topic_report_cleaned[internal_keyword_col].map(onsite_searches_series).fillna(0)
        else:
            df_for_topic_report_cleaned['On-Site Searches'] = 0

        topic_keywords_map_by_topicid_local = df_for_topic_report_cleaned.groupby('TopicID')[internal_keyword_col].unique().apply(list).to_dict()
        
        agg_ops = {
            'TotalMonthlyGoogleSearches': (internal_volume_col, 'sum'),
            'TotalCompetitorMonthlyOrganicTraffic': (internal_traffic_col, 'sum'),
            'OnSiteSearches': ('On-Site Searches', 'sum'),
            'CompetitorAvgRank': (internal_position_col, 'mean'),
            'KeywordCount': (internal_keyword_col, 'nunique')
        }
        if not internal_volume_col: agg_ops.pop('TotalMonthlyGoogleSearches', None)
        if not internal_traffic_col: agg_ops.pop('TotalCompetitorMonthlyOrganicTraffic', None)

        topic_agg_by_topicid = df_for_topic_report_cleaned.groupby('TopicID').agg(**agg_ops).reset_index()
        topic_agg_by_topicid['Keyword Group'] = topic_agg_by_topicid['TopicID'].map(topic_names).fillna('Uncategorized')
        
        return topic_agg_by_topicid, topic_keywords_map_by_topicid_local

    def create_threat_topic_report(df_for_threats_input):
        if df_for_threats_input.empty: return [], {}
        master_keyword_group_map = master_df.drop_duplicates(subset=[internal_keyword_col])[[internal_keyword_col, 'TopicID', 'Keyword Group']].copy()
        
        df_with_groups = pd.merge(df_for_threats_input, master_keyword_group_map, left_on='Keyword', right_on=internal_keyword_col, how='left')
        
        keyword_map = df_with_groups.groupby('TopicID')['Keyword'].unique().apply(list).to_dict()
        agg_dict = {'AvgOurRank': ('Our Rank', 'mean'), 'AvgBestCompetitorRank': ('Best Competitor Rank', 'mean'), 'TotalOurTraffic': ('Our Monthly Organic Traffic', 'sum'), 'TotalBestCompetitorTraffic': ('Best Competitor Monthly Organic Traffic', 'sum'), 'TotalTrafficGrowthOpportunity': ('Traffic Growth Opportunity', 'sum'), 'KeywordCount': ('Keyword', 'nunique')}
        if 'Monthly Google Searches' in df_for_threats_input.columns: agg_dict['TotalMonthlyGoogleSearches'] = ('Monthly Google Searches', 'sum')
        
        topic_threats_agg = df_with_groups.groupby('TopicID').agg(**agg_dict).reset_index()
        topic_threats_agg['Keyword Group'] = topic_threats_agg['TopicID'].map(topic_names).fillna('Uncategorized')
        
        rename_dict = {
            "AvgOurRank": "Avg Our Rank",
            "TotalOurTraffic": "Total Our Traffic",
            "AvgBestCompetitorRank": "Avg Best Competitor Rank",
            "TotalBestCompetitorTraffic": "Total Best Competitor Traffic",
            "TotalTrafficGrowthOpportunity": "Total Traffic Growth Opportunity",
            "TotalMonthlyGoogleSearches": "Total Monthly Google Searches",
            "KeywordCount": "Keyword Count"
        }
        topic_threats_agg.rename(columns=rename_dict, inplace=True)

        if 'Avg Our Rank' in topic_threats_agg.columns:
            topic_threats_agg['Avg Our Rank'] = topic_threats_agg['Avg Our Rank'].round(2)
        if 'Avg Best Competitor Rank' in topic_threats_agg.columns:
            topic_threats_agg['Avg Best Competitor Rank'] = topic_threats_agg['Avg Best Competitor Rank'].round(2)

        topic_threats_agg.replace({np.nan: None}, inplace=True)
        return topic_threats_agg.to_dict(orient='records'), keyword_map

    def report(message, current, total):
        if progress_reporter:
            progress_reporter(message, current, total)

    total_steps = 4 

    report("Parsing and validating inputs...", 1, total_steps)
    try:
        options = json.loads(options_str)
        internal_keyword_col = options['columnMap']['keywordCol'].replace(' ', '').replace('_', '')
        internal_position_col = options['columnMap']['positionCol'].replace(' ', '').replace('_', '')
        internal_url_col_name = options['columnMap']['urlCol'].replace(' ', '').replace('_', '')
        internal_volume_col = options['columnMap'].get('volumeCol', '').replace(' ', '').replace('_', '')
        internal_traffic_col = options['columnMap'].get('trafficCol', '').replace(' ', '').replace('_', '')
        onsite_date_range = options.get('onsiteDateRange', '')
        excluded_keywords = options.get('excludedKeywords', [])
        # *** NEW: Get the lens selections from the options payload ***
        lenses_to_run = options.get('lensesToRun', {})
    except (json.JSONDecodeError, KeyError) as e:
        raise ValueError(f"Invalid or missing options provided in request: {e}")
    
    # *** NEW: Initialize all report variables to be empty by default ***
    keyword_gap_report_raw, topic_gap_report_raw, core_topic_gap_report_raw = [], [], []
    topic_keyword_map_by_topicid, core_topic_keyword_map_by_topicid = {}, {}
    keyword_threats_report_raw, topic_threats_report_raw, core_topic_threats_report_raw = [], [], []
    topic_threats_keyword_map_by_topicid, core_topic_threats_keyword_map_by_topicid = {}, {}
    keyword_market_share_report_raw, group_market_share_report_raw, core_group_market_share_report_raw = [], [], []
    group_market_share_keyword_map, core_group_market_share_keyword_map = {}, {}
    category_overhaul_matrix_report_raw, facet_potential_report_raw = [], []

    with open(our_file_path, 'rb') as f:
        our_df = utils.read_csv_with_encoding_fallback(f)
    if our_df is None: raise ValueError("Could not read your domain's CSV file.")
    
    original_our_df_cols = our_df.columns.tolist()
    rename_map_our = {col: col.replace(' ', '').replace('_', '') for col in original_our_df_cols}
    our_df.rename(columns=rename_map_our, inplace=True)
    
    if our_df.columns.has_duplicates:
        our_df = our_df.groupby(level=0, axis=1).apply(lambda group: group.ffill(axis=1).bfill(axis=1).iloc[:, 0])
    
    cols_to_drop_our = [col for col in our_df.columns if col.lower() in COLS_TO_EXCLUDE_AT_SOURCE]
    if cols_to_drop_our:
        our_df.drop(columns=cols_to_drop_our, inplace=True)

    if internal_keyword_col in our_df.columns:
        our_df[internal_keyword_col] = our_df[internal_keyword_col].astype(str).str.strip().str.lower()

    required_internal_cols = {internal_keyword_col, internal_position_col, internal_url_col_name}
    if not required_internal_cols.issubset(our_df.columns):
        missing_original = ", ".join([col for col in options['columnMap'].values() if col.replace(' ', '').replace('_', '') not in our_df.columns])
        raise ValueError(f"Your main file is missing required columns based on your mapping: {missing_original}")
    
    our_domain = next((d for d in (utils.get_domain_from_url(url) for url in our_df[internal_url_col_name].head(10)) if d), None)
    if not our_domain: raise ValueError(f"Could not determine your domain from the URL column.")
    our_df['Source'] = our_domain
    
    competitor_dfs, competitor_domains = [], []
    for f_path in competitor_file_paths:
        with open(f_path, 'rb') as f_stream:
            df = utils.read_csv_with_encoding_fallback(f_stream)
            if df is not None:
                original_comp_df_cols = df.columns.tolist()
                rename_map_comp = {col: col.replace(' ', '').replace('_', '') for col in original_comp_df_cols}
                df.rename(columns=rename_map_comp, inplace=True)

                if df.columns.has_duplicates:
                    df = df.groupby(level=0, axis=1).apply(lambda group: group.ffill(axis=1).bfill(axis=1).iloc[:, 0])

                cols_to_drop_comp = [col for col in df.columns if col.lower() in COLS_TO_EXCLUDE_AT_SOURCE]
                if cols_to_drop_comp:
                    df.drop(columns=cols_to_drop_comp, inplace=True)

                if internal_keyword_col in df.columns:
                    df[internal_keyword_col] = df[internal_keyword_col].astype(str).str.strip().str.lower()
                if internal_url_col_name in df.columns:
                    comp_domain = next((d for d in (utils.get_domain_from_url(url) for url in df[internal_url_col_name].head(10)) if d and d != our_domain), None)
                    if comp_domain:
                        df['Source'] = comp_domain
                        competitor_domains.append(comp_domain)
                        competitor_dfs.append(df)

    all_dfs = [our_df] + competitor_dfs
    master_df = pd.concat(all_dfs, ignore_index=True)

    if excluded_keywords:
        print(f"Excluding {len(excluded_keywords)} branded terms...")
        exclude_pattern = '|'.join([re.escape(kw) for kw in excluded_keywords])
        initial_rows = len(master_df)
        master_df = master_df[~master_df[internal_keyword_col].str.contains(exclude_pattern, case=False, na=False)]
        print(f"Removed {initial_rows - len(master_df)} rows containing branded keywords.")
    
    for col in [internal_position_col, internal_volume_col, internal_traffic_col]:
        if col and col in master_df.columns: 
            master_df[col] = pd.to_numeric(master_df[col], errors='coerce')

    has_onsite_data = False
    onsite_df = None
    if onsite_file_path:
        with open(onsite_file_path, 'rb') as f:
            onsite_df_raw = utils.read_csv_with_encoding_fallback(f)
            if onsite_df_raw is not None and len(onsite_df_raw.columns) >= 2:
                onsite_df_raw.columns = ['keyword', 'searches']
                onsite_df_raw['keyword'] = onsite_df_raw['keyword'].astype(str).str.strip().str.lower()
                onsite_df_raw['searches'] = pd.to_numeric(onsite_df_raw['searches'], errors='coerce').fillna(0).astype(int)
                onsite_df = onsite_df_raw.groupby('keyword')['searches'].sum().reset_index()
                has_onsite_data = True

    # *** NEW: Determine if expensive clustering is needed based on lens selection ***
    needs_clustering = any([
        lenses_to_run.get('content_gaps'), 
        lenses_to_run.get('competitive_opportunities'), 
        lenses_to_run.get('market_share')
    ])
    
    topic_names = {}
    if needs_clustering:
        report("Performing semantic clustering...", 2, total_steps)
        master_df_for_clustering = master_df.dropna(subset=[internal_keyword_col]).copy()
        master_df['TopicID'] = analysis.perform_topic_clustering(master_df_for_clustering, internal_keyword_col)
        master_df = master_df[master_df['TopicID'] != -1].copy()
        
        prelim_keywords_df = pd.DataFrame() 
        if has_onsite_data:
            prelim_keywords_df = master_df.drop_duplicates(subset=[internal_keyword_col]).copy()
            prelim_keywords_df['lower_keyword'] = prelim_keywords_df[internal_keyword_col].str.lower()
            
            if internal_traffic_col:
                comp_traffic_df = master_df[master_df['Source'] != our_domain]
                if not comp_traffic_df.empty:
                    top_comp_traffic = comp_traffic_df.loc[comp_traffic_df.groupby(internal_keyword_col)[internal_traffic_col].idxmax()]
                    prelim_keywords_df = pd.merge(prelim_keywords_df, top_comp_traffic[[internal_keyword_col, internal_traffic_col]], on=internal_keyword_col, how='left')
                    prelim_keywords_df.rename(columns={internal_traffic_col: 'Top Competitor Traffic'}, inplace=True)

            prelim_keywords_df = pd.merge(prelim_keywords_df, onsite_df, left_on='lower_keyword', right_on='keyword', how='left')
            prelim_keywords_df.rename(columns={'searches': 'On-Site Searches'}, inplace=True)
            
            scaler = MinMaxScaler()
            score_cols = [internal_volume_col, 'Top Competitor Traffic', 'On-Site Searches']
            valid_score_cols = [col for col in score_cols if col in prelim_keywords_df.columns and not prelim_keywords_df[col].isnull().all()]
            
            if len(valid_score_cols) > 0:
                prelim_keywords_df[valid_score_cols] = prelim_keywords_df[valid_score_cols].fillna(0)
                normalized_data = scaler.fit_transform(prelim_keywords_df[valid_score_cols])
                normalized_df = pd.DataFrame(normalized_data, columns=valid_score_cols, index=prelim_keywords_df.index)
                
                weights = {internal_volume_col: 0.40, 'Top Competitor Traffic': 0.35, 'On-Site Searches': 0.25}
                prelim_keywords_df['Opportunity Score'] = sum(normalized_df.get(col, 0) * weights[col] for col in valid_score_cols if col in weights) * 100
                prelim_keywords_df['Opportunity Score'] = prelim_keywords_df['Opportunity Score'].round(0)
            else:
                 prelim_keywords_df['Opportunity Score'] = 0

            top_keywords_per_topic = prelim_keywords_df.sort_values('Opportunity Score', ascending=False).groupby('TopicID').head(3)
            topic_names = top_keywords_per_topic.groupby('TopicID')[internal_keyword_col].apply(lambda x: ', '.join(x)).to_dict()
        elif internal_volume_col in master_df.columns and not master_df[internal_volume_col].isnull().all():
            top_keywords_per_topic = master_df.sort_values(internal_volume_col, ascending=False).groupby('TopicID').head(3)
            topic_names = top_keywords_per_topic.groupby('TopicID')[internal_keyword_col].apply(lambda x: ', '.join(x)).to_dict()

        master_df['Keyword Group'] = master_df['TopicID'].map(topic_names).fillna('Uncategorized')
    else:
        # If clustering is skipped, provide default columns to prevent errors
        report("Skipping semantic clustering as per user selection...", 2, total_steps)
        master_df['TopicID'] = -1
        master_df['Keyword Group'] = 'N/A'


    report("Generating analysis reports...", 3, total_steps)
    our_ranking_keywords = master_df[master_df['Source'] == our_domain][internal_keyword_col].unique()

    # *** NEW: Conditional 'Content Gaps' Analysis ***
    if lenses_to_run.get('content_gaps'):
        competitor_only_df = master_df[~master_df[internal_keyword_col].isin(our_ranking_keywords)].copy()

        if not competitor_only_df.empty:
            def get_gap_details(group):
                top_ranker = group.loc[group[internal_position_col].idxmin()]
                details = {
                    'Monthly Google Searches': group[internal_volume_col].iloc[0] if internal_volume_col in group.columns else 0,
                    '# Ranking Competitors': group['Source'].nunique(),
                    'Highest Competitor Rank': top_ranker[internal_position_col],
                    'Top Ranking Competitor': top_ranker['Source'],
                    'Top Competitor URL': top_ranker[internal_url_col_name],
                    'Top Competitor Monthly Organic Traffic': top_ranker.get(internal_traffic_col, 0) if internal_traffic_col in group.columns else 0,
                }
                return pd.Series(details)
            
            keyword_gap_agg = competitor_only_df.groupby(internal_keyword_col).apply(get_gap_details, include_groups=False).reset_index()
            
            if has_onsite_data:
                keyword_gap_agg['lower_keyword'] = keyword_gap_agg[internal_keyword_col].str.lower()
                keyword_gap_agg = pd.merge(keyword_gap_agg, onsite_df, left_on='lower_keyword', right_on='keyword', how='left')
                keyword_gap_agg.rename(columns={'searches': 'On-Site Searches'}, inplace=True)
                
                # Re-use prelim_keywords_df if it was created during clustering
                if 'Opportunity Score' in locals().get('prelim_keywords_df', pd.DataFrame()).columns:
                    scores_to_merge = prelim_keywords_df[['lower_keyword', 'Opportunity Score']]
                    keyword_gap_agg = pd.merge(keyword_gap_agg, scores_to_merge, on='lower_keyword', how='left')

                keyword_gap_agg.drop(columns=['lower_keyword','keyword'], inplace=True, errors='ignore')
            else:
                keyword_gap_agg['On-Site Searches'] = 0
            
            keyword_gap_agg.replace({np.nan: None}, inplace=True)
            keyword_gap_report_raw = keyword_gap_agg.rename(columns={internal_keyword_col: 'Keyword'}).to_dict(orient='records')

            for scope in ['full', 'core']:
                report_df = competitor_only_df if scope == 'full' else competitor_only_df[competitor_only_df[internal_position_col] <= 20]
                if report_df.empty:
                    if scope == 'full': topic_gap_report_raw, topic_keyword_map_by_topicid = [], {}
                    else: core_topic_gap_report_raw, core_topic_keyword_map_by_topicid = [], {}
                    continue

                topic_agg_df, topic_map = create_topic_report(report_df, onsite_df)

                if has_onsite_data and not topic_agg_df.empty:
                    score_cols_agg = ['TotalMonthlyGoogleSearches', 'TotalCompetitorMonthlyOrganicTraffic', 'OnSiteSearches']
                    valid_score_cols_agg = [col for col in score_cols_agg if col in topic_agg_df.columns]
                    
                    if len(valid_score_cols_agg) > 0:
                        scaler_agg = MinMaxScaler()
                        topic_agg_df[valid_score_cols_agg] = topic_agg_df[valid_score_cols_agg].fillna(0)
                        normalized_data_agg = scaler_agg.fit_transform(topic_agg_df[valid_score_cols_agg])
                        normalized_df_agg = pd.DataFrame(normalized_data_agg, columns=valid_score_cols_agg, index=topic_agg_df.index)
                        
                        weights_agg = {'TotalMonthlyGoogleSearches': 0.40, 'TotalCompetitorMonthlyOrganicTraffic': 0.35, 'OnSiteSearches': 0.25}
                        topic_agg_df['Opportunity Score'] = sum(normalized_df_agg.get(col, 0) * weights_agg.get(col, 0) for col in valid_score_cols_agg) * 100

                rename_dict = {
                    "TotalMonthlyGoogleSearches": "Total Monthly Google Searches",
                    "TotalCompetitorMonthlyOrganicTraffic": "Total Competitor Monthly Organic Traffic",
                    "OnSiteSearches": "Total On-Site Searches",
                    "CompetitorAvgRank": "Competitor Avg. Rank",
                    "KeywordCount": "Gap Keyword Count"
                }
                topic_agg_df.rename(columns=rename_dict, inplace=True)

                if 'Opportunity Score' in topic_agg_df.columns:
                    topic_agg_df['Opportunity Score'] = topic_agg_df['Opportunity Score'].round(0)
                if 'Competitor Avg. Rank' in topic_agg_df.columns:
                    topic_agg_df['Competitor Avg. Rank'] = topic_agg_df['Competitor Avg. Rank'].round(2)
                
                topic_agg_df.replace({np.nan: None}, inplace=True)
                
                if scope == 'full':
                    topic_gap_report_raw = topic_agg_df.to_dict(orient='records')
                    topic_keyword_map_by_topicid = topic_map
                else:
                    core_topic_gap_report_raw = topic_agg_df.to_dict(orient='records')
                    core_topic_keyword_map_by_topicid = topic_map

    # *** NEW: Conditional 'Competitive Opportunities' Analysis ***
    if lenses_to_run.get('competitive_opportunities'):
        shared_keywords_df = master_df[master_df[internal_keyword_col].isin(our_ranking_keywords)].copy()
        if not shared_keywords_df.empty:
            our_data = shared_keywords_df[shared_keywords_df['Source'] == our_domain]
            comp_data = shared_keywords_df[shared_keywords_df['Source'] != our_domain]

            if not comp_data.empty:
                best_comp_data = comp_data.loc[comp_data.groupby(internal_keyword_col)[internal_position_col].idxmin()]

                cols_to_merge = [internal_keyword_col, internal_position_col, internal_url_col_name, 'Source']
                if internal_traffic_col: cols_to_merge.append(internal_traffic_col)
                if internal_volume_col: cols_to_merge.append(internal_volume_col)
                
                combined = pd.merge(
                    our_data, 
                    best_comp_data, 
                    on=internal_keyword_col, 
                    how='inner',
                    suffixes=('_Our', '_Comp')
                )

                col_our, col_comp = f'{internal_position_col}_Our', f'{internal_position_col}_Comp'
                combined.dropna(subset=[col_our, col_comp], inplace=True)
                leakage_df = combined[combined[col_comp] < combined[col_our]].copy()
                
                traffic_cols_available = internal_traffic_col and f'{internal_traffic_col}_Our' in leakage_df.columns and f'{internal_traffic_col}_Comp' in leakage_df.columns
                if not leakage_df.empty and traffic_cols_available:
                    leakage_df[f'{internal_traffic_col}_Our'] = leakage_df[f'{internal_traffic_col}_Our'].fillna(0)
                    leakage_df[f'{internal_traffic_col}_Comp'] = leakage_df[f'{internal_traffic_col}_Comp'].fillna(0)

                    leakage_df['TrafficGrowthOpportunity'] = leakage_df[f'{internal_traffic_col}_Comp'] - leakage_df[f'{internal_traffic_col}_Our']
                    
                    final_cols_map = {
                        internal_keyword_col: 'Keyword', f'{internal_volume_col}_Our': 'Monthly Google Searches', f'{internal_position_col}_Our': 'Our Rank',
                        f'{internal_url_col_name}_Our': 'Our URL', f'{internal_traffic_col}_Our': 'Our Monthly Organic Traffic', 'Source_Comp': 'Best Competitor',
                        f'{internal_position_col}_Comp': 'Best Competitor Rank', f'{internal_url_col_name}_Comp': 'Best Competitor URL',
                        f'{internal_traffic_col}_Comp': 'Best Competitor Monthly Organic Traffic', 'TrafficGrowthOpportunity': 'Traffic Growth Opportunity'
                    }

                    filtered_final_cols_map = {k: v for k, v in final_cols_map.items() if k in leakage_df.columns}
                    keyword_threats_df = leakage_df[list(filtered_final_cols_map.keys())].rename(columns=filtered_final_cols_map)
                    
                    keyword_threats_df.replace({np.nan: None}, inplace=True)
                    keyword_threats_report_raw = keyword_threats_df.to_dict(orient='records')
                    
                    topic_threats_report_raw, topic_threats_keyword_map_by_topicid = create_threat_topic_report(keyword_threats_df)
                    
                    core_leakage_df = keyword_threats_df.dropna(subset=['Best Competitor Rank'])
                    core_leakage_df = core_leakage_df[core_leakage_df['Best Competitor Rank'] <= 10].copy()
                    core_topic_threats_report_raw, core_topic_threats_keyword_map_by_topicid = create_threat_topic_report(core_leakage_df)

    # *** NEW: Conditional 'Market Share' Analysis ***
    if lenses_to_run.get('market_share') and internal_traffic_col:
        keyword_market_share_report_raw = _calculate_keyword_market_share(master_df, internal_keyword_col, 'Source', internal_traffic_col)
        
        group_market_share_df = _calculate_group_market_share(master_df, 'Keyword Group', 'Source', internal_traffic_col)
        if not group_market_share_df.empty:
            group_market_share_keyword_map = master_df.groupby('Keyword Group')[internal_keyword_col].unique().apply(list).to_dict()
            group_market_share_df['Keyword Count'] = group_market_share_df['Keyword Group'].map(lambda g: len(group_market_share_keyword_map.get(g, [])))
            group_market_share_df.replace({np.nan: None}, inplace=True)
            group_market_share_report_raw = group_market_share_df.to_dict(orient='records')

        core_master_df = master_df[master_df[internal_position_col] <= 20].copy()
        core_group_market_share_df = _calculate_group_market_share(core_master_df, 'Keyword Group', 'Source', internal_traffic_col)
        if not core_group_market_share_df.empty:
            core_group_market_share_keyword_map = core_master_df.groupby('Keyword Group')[internal_keyword_col].unique().apply(list).to_dict()
            core_group_market_share_df['Keyword Count'] = core_group_market_share_df['Keyword Group'].map(lambda g: len(core_group_market_share_keyword_map.get(g, [])))
            core_group_market_share_df.replace({np.nan: None}, inplace=True)
            core_group_market_share_report_raw = core_group_market_share_df.to_dict(orient='records')

    report("Generating Category Overhaul Matrix...", 4, total_steps)
    # *** NEW: Conditional 'Taxonomy & Architecture' Analysis ***
    if lenses_to_run.get('taxonomy_analysis'):
        overhaul_results = _generate_category_overhaul_matrix(
            master_df.copy(),
            internal_keyword_col=internal_keyword_col,
            internal_position_col=internal_position_col,
            internal_traffic_col=internal_traffic_col,
            internal_url_col_name=internal_url_col_name,
            onsite_df=onsite_df,
            internal_volume_col=internal_volume_col
        )
        category_overhaul_matrix_report_raw = overhaul_results["matrix_report"]
        facet_potential_report_raw = overhaul_results["facet_potential_report"]
    else:
        print("Skipping Taxonomy & Architecture analysis as per user request.")

    return {
        "keywordGapReport": keyword_gap_report_raw,
        "topicGapReport": topic_gap_report_raw,
        "coreTopicGapReport": core_topic_gap_report_raw,
        "topicKeywordMap": topic_keyword_map_by_topicid,
        "coreTopicKeywordMap": core_topic_keyword_map_by_topicid,
        "keywordThreatsReport": keyword_threats_report_raw,
        "topicThreatsReport": topic_threats_report_raw,
        "coreTopicThreatsReport": core_topic_threats_report_raw,
        "topicThreatsKeywordMap": topic_threats_keyword_map_by_topicid,
        "coreTopicThreatsKeywordMap": core_topic_threats_keyword_map_by_topicid,
        "keywordMarketShareReport": keyword_market_share_report_raw,
        "groupMarketShareReport": group_market_share_report_raw,
        "coreGroupMarketShareReport": core_group_market_share_report_raw,
        "groupMarketShareKeywordMap": group_market_share_keyword_map,
        "coreGroupMarketShareKeywordMap": core_group_market_share_keyword_map,
        "categoryOverhaulMatrixReport": category_overhaul_matrix_report_raw,
        "facetPotentialReport": facet_potential_report_raw,
        "hasOnsiteData": has_onsite_data,
        "columnMap": options['columnMap'],
        "ourDomain": our_domain,
        "competitorDomains": competitor_domains,
        "onsiteDateRange": onsite_date_range,
    }