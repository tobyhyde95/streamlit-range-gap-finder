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

# Import the enhanced URL parser
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


def _generate_category_overhaul_matrix(
    df,
    internal_keyword_col,
    internal_position_col,
    internal_traffic_col,
    internal_url_col_name,
    onsite_df,
    internal_volume_col,
    topic_col='TopicID',
    enable_enhanced_parsing=True,
    enable_synonym_discovery=True
):
    """
    Generates a matrix of categories and facets using a "learn and classify" model.
    Returns detailed matrix and a high-level facet potential report.
    Now supports enhanced URL parsing with configurable patterns and synonym discovery.
    """
    if df.empty or internal_traffic_col not in df.columns:
        return {
            "matrix_report": [],
            "facet_potential_report": []
        }

    # Initialize enhanced URL parser and synonym discovery
    url_parser = URLParser() if enable_enhanced_parsing else None
    synonym_discovery = SynonymDiscovery() if enable_synonym_discovery else None
    
    stemmer = PorterStemmer()
    df_sorted = df.sort_values([internal_keyword_col, internal_position_col], ascending=[True, True])
    highest_ranking_df = df_sorted.drop_duplicates(subset=[internal_keyword_col], keep='first').copy()

    print("Learning category candidates from URL structures...")
    
    unique_urls = highest_ranking_df[internal_url_col_name].dropna().unique()
    
    if enable_enhanced_parsing and url_parser:
        print("Using enhanced URL parser with configurable patterns...")
        
        # Use enhanced category extraction
        highest_ranking_df['Original Category Mapping'] = highest_ranking_df[internal_url_col_name].apply(
            lambda url: url_parser.extract_category_from_url(url)
        )
        
        # Discover synonyms if enabled
        if enable_synonym_discovery and synonym_discovery:
            print("Discovering potential synonyms from URLs...")
            candidates = synonym_discovery.discover_synonyms_from_urls(unique_urls.tolist())
            if candidates:
                stored_ids = synonym_discovery.store_candidates(candidates)
                print(f"Discovered {len(candidates)} potential synonyms, stored {len(stored_ids)} in database")
        
        # Get strong candidates from the enhanced extraction
        category_counts = highest_ranking_df['Original Category Mapping'].value_counts()
        min_freq = max(2, int(len(unique_urls) * 0.01))
        strong_candidates = set(category_counts[category_counts >= min_freq].index)
        
    else:
        print("Using legacy URL parsing...")
        # Legacy logic for backward compatibility
        all_segments = []
        for url in unique_urls:
            try:
                path_segments = [
                    s.replace('-', ' ').replace('_', ' ')
                    for s in urlparse(str(url)).path.lower().strip('/').split('/')
                    if re.search(r'[a-zA-Z]', s) and len(s) > 3 and not re.search(r'\d', s)
                ]
                all_segments.extend(path_segments)
            except Exception:
                continue

        segment_freq = Counter(all_segments)
        min_freq = max(2, int(len(unique_urls) * 0.01))
        strong_candidates = {segment for segment, freq in segment_freq.items() if freq >= min_freq}

        def find_best_category(url, candidates):
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
        
        # This line is already handled in the enhanced parsing section above
        pass

    if onsite_df is not None and not onsite_df.empty:
        highest_ranking_df = pd.merge(highest_ranking_df, onsite_df, left_on=internal_keyword_col, right_on='keyword', how='left')
        highest_ranking_df.rename(columns={'searches': 'On-Site Searches'}, inplace=True)
        highest_ranking_df.drop(columns=['keyword'], inplace=True, errors='ignore')

    highest_ranking_df['On-Site Searches'] = highest_ranking_df.get('On-Site Searches', pd.Series(0, index=highest_ranking_df.index)).fillna(0).astype(int)
    # Original Category Mapping is already set in the enhanced parsing section above

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

        # Pre-compute spaCy docs for canonical categories to avoid repeated processing
        canonical_docs = {}
        if canonical_categories_set:
            print(f"Pre-computing spaCy docs for {len(canonical_categories_set)} canonical categories...")
            for canon_cat in canonical_categories_set:
                canonical_docs[canon_cat] = nlp(canon_cat.lower())

        print(f"Processing {len(unique_original_cats)} unique categories for decompounding...")
        for idx, cat_str in enumerate(unique_original_cats):
            if idx % 100 == 0 and idx > 0:
                print(f"Processed {idx}/{len(unique_original_cats)} categories...")
            
            doc = nlp(cat_str.lower())
            root = next((token for token in doc if token.head == token), None)
            potential_cat_word = root.lemma_ if root else None
            final_category = None

            if potential_cat_word and canonical_categories_set:
                # Pre-compute the potential category word doc once
                potential_doc = nlp(potential_cat_word)
                
                # Skip if the doc has no vector (to avoid the empty vector warning)
                if not potential_doc.has_vector:
                    final_category = cat_str
                    derived_facets = None
                    type_facet = None
                else:
                    best_match, best_match_sim = None, 0.0
                    for canon_cat, canon_doc in canonical_docs.items():
                        # Skip if canonical doc has no vector
                        if not canon_doc.has_vector:
                            continue
                        sim = potential_doc.similarity(canon_doc)
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
                        if enable_enhanced_parsing and url_parser:
                            # Use enhanced URL parser for category extraction
                            extracted_cat = url_parser.extract_category_from_url(row[internal_url_col_name])
                            if extracted_cat and extracted_cat != current_cat:
                                return extracted_cat
                        else:
                            # Legacy URL parsing
                            url_path = urlparse(str(row[internal_url_col_name])).path.lower().strip('/')
                            if url_path == current_cat.lower().replace(' ', '-'):
                                return current_cat
                    except Exception:
                        pass
                    kw_tokens = set(str(row[internal_keyword_col]).lower().split())
                    for strong_cat in strong_categories_from_traffic:
                        strong_cat_forms = get_word_forms(strong_cat.lower())
                        if not kw_tokens.isdisjoint(strong_cat_forms):
                            return strong_cat
                return current_cat

            highest_ranking_df['Category Mapping'] = highest_ranking_df.swifter.apply(reclassify_row, axis=1)

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
            if enable_enhanced_parsing and url_parser:
                # Use enhanced facet normalization
                raw_facets = parse_qs(urlparse(str(url)).query)
                normalized_facets = {}
                for key, values in raw_facets.items():
                    if values:
                        normalized_key = url_parser.normalize_facet_key(key)
                        normalized_facets[normalized_key] = clean_facet_value(values[0])
                return normalized_facets
            else:
                # Legacy facet extraction
                return {k.lower(): clean_facet_value(v[0]) for k, v in parse_qs(urlparse(str(url)).query).items() if v}
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

    highest_ranking_df = pd.concat([highest_ranking_df, explicit_facets_df], axis=1)
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

    print("Performing granular facet consolidation...")
    cols_to_process = [col for col in potential_facet_cols if col in highest_ranking_df.columns and highest_ranking_df[col].count() > 0]
    processed_pairs = set()
    for i in range(len(cols_to_process)):
        for j in range(i + 1, len(cols_to_process)):
            col_A_name = cols_to_process[i]
            col_B_name = cols_to_process[j]
            if (col_B_name, col_A_name) in processed_pairs:
                continue
            processed_pairs.add((col_A_name, col_B_name))
            values_A = set(highest_ranking_df[col_A_name].dropna().unique())
            values_B = set(highest_ranking_df[col_B_name].dropna().unique())
            common_values = values_A.intersection(values_B)
            if not common_values:
                continue
            count_A = highest_ranking_df[col_A_name].count()
            count_B = highest_ranking_df[col_B_name].count()
            if count_A >= count_B:
                primary_col_name, secondary_col_name = col_A_name, col_B_name
                values_secondary = values_B
            else:
                primary_col_name, secondary_col_name = col_B_name, col_A_name
                values_secondary = values_A
            duplication_rate = len(common_values) / len(values_secondary) if len(values_secondary) > 0 else 0
            DUPLICATION_THRESHOLD = 0.5
            if duplication_rate > DUPLICATION_THRESHOLD:
                mask = highest_ranking_df[secondary_col_name].isin(common_values)
                highest_ranking_df.loc[mask, primary_col_name] = highest_ranking_df.loc[mask, primary_col_name].fillna(highest_ranking_df.loc[mask, secondary_col_name])
                highest_ranking_df.loc[mask, secondary_col_name] = np.nan

    if nlp:
        ATTRIBUTE_SEEDS = nlp("material color size power type feature brand style finish")
        NOISE_SEEDS = nlp("opinion deal location guide review good best cheap sale offer")

    dynamic_noise_set = set()
    if topic_col in highest_ranking_df.columns and highest_ranking_df[topic_col].nunique() > 1 and nlp:
        print("Generating dynamic noise filter based on term frequency across topics...")
        topic_docs = highest_ranking_df.dropna(subset=[internal_keyword_col, topic_col]).groupby(topic_col)[internal_keyword_col].apply(lambda x: ' '.join(x))
        word_in_topic_count = Counter()
        for doc in topic_docs:
            words_in_doc = {token.lemma_ for token in nlp(doc.lower()) if token.is_alpha and len(token.lemma_) > 2}
            for word in words_in_doc:
                word_in_topic_count[word] += 1
        num_topics = highest_ranking_df[topic_col].nunique()
        noise_threshold = 0.30
        for word, count in word_in_topic_count.items():
            if (count / num_topics) > noise_threshold:
                dynamic_noise_set.add(word)

    def discover_remaining_facets(row, learned_noise_tokens):
        if nlp is None:
            return None
        ignore_tokens = learned_noise_tokens.copy()
        for token in nlp.Defaults.stop_words:
            ignore_tokens.add(token)
        if pd.notnull(row['Category Mapping']):
            for cat_word in str(row['Category Mapping']).lower().split():
                ignore_tokens.update(get_word_forms(cat_word))
        assigned_facet_values = set()
        facet_cols_in_row = [c for c in potential_facet_cols if c in row and pd.notnull(row[c])]
        facet_cols_in_row.append('Derived Facets')
        for col in facet_cols_in_row:
            if col in row and pd.notnull(row[col]):
                values = str(row[col]).split(' | ')
                for val in values:
                    assigned_facet_values.update(val.strip().lower().split())
        ignore_tokens.update(assigned_facet_values)
        kw_text = str(row[internal_keyword_col]).lower()
        doc = nlp(kw_text)
        discovered = set()
        if 'heavy duty' in kw_text:
            discovered.add('Heavy Duty')
            kw_text = kw_text.replace('heavy duty', '')
        doc = nlp(kw_text)
        potential_tokens = [
            token for token in doc
            if token.pos_ in ['NOUN', 'PROPN', 'ADJ'] and not token.is_stop and token.is_alpha and len(token.lemma_) > 2 and token.lemma_ not in ignore_tokens
        ]
        for token in potential_tokens:
            attribute_similarity = token.similarity(ATTRIBUTE_SEEDS)
            noise_similarity = token.similarity(NOISE_SEEDS)
            is_location = any(ent.label_ == 'GPE' for ent in nlp(token.text).ents)
            if attribute_similarity > (noise_similarity * 1.1) and not is_location:
                discovered.add(token.lemma_.title())
        return ', '.join(sorted(list(discovered))) if discovered else None

    highest_ranking_df['Discovered Facets'] = highest_ranking_df.swifter.apply(
        discover_remaining_facets,
        learned_noise_tokens=dynamic_noise_set,
        axis=1
    )

    def _organize_facets(df, explicit_cols_df):
        print("Organizing and classifying discovered facets...")
        known_brands = set()
        if not explicit_cols_df.empty:
            for col in explicit_cols_df.columns:
                if col.lower() in ['brand', 'make', 'manufacturer']:
                    known_brands.update([b.lower() for b in explicit_cols_df[col].dropna().unique()])
        all_keywords_text = ' '.join(df[internal_keyword_col].dropna().unique())
        if nlp:
            kw_doc = nlp(all_keywords_text)
            known_brands.update({ent.text.lower() for ent in kw_doc.ents if ent.label_ == 'ORG'})

        def _find_brand_column(cols_df, brands_set):
            for col in cols_df.columns:
                if col.lower() in ['brand', 'make', 'manufacturer']:
                    return col
            for col in cols_df.columns:
                values = cols_df[col].dropna().str.lower().unique()
                if len(values) == 0:
                    continue
                matches = sum(1 for v in values if v in brands_set)
                if (matches / len(values)) > 0.5:
                    return col
            return None

        brand_col_name = _find_brand_column(explicit_facets_df, known_brands)
        new_facet_cols = defaultdict(list)
        discovered_brands = []
        for _, row in df.iterrows():
            discovered_str = row.get('Discovered Facets', '')
            facets = set(discovered_str.split(', ')) if pd.notnull(discovered_str) and discovered_str else set()
            row_brands, row_voltages, row_powers, row_features = set(), set(), set(), set()
            for facet in facets:
                f_lower = facet.lower()
                if f_lower in known_brands:
                    row_brands.add(facet.title())
                elif re.search(r'\d+v', f_lower):
                    row_voltages.add(facet)
                elif f_lower in ['cordless', 'corded', 'electric', 'petrol', 'battery']:
                    row_powers.add(facet.title())
                else:
                    row_features.add(facet.title())
            discovered_brands.append(', '.join(sorted(row_brands)) if row_brands else None)
            new_facet_cols['Voltage'].append(', '.join(sorted(row_voltages)) if row_voltages else None)
            new_facet_cols['Power Source'].append(', '.join(sorted(row_powers)) if row_powers else None)
            new_facet_cols['Features'].append(', '.join(sorted(row_features)) if row_features else None)

        if brand_col_name:
            df[brand_col_name] = df[brand_col_name].astype(str).replace('nan', '')
            discovered_brands_series = pd.Series(discovered_brands, index=df.index).fillna('')
            df[brand_col_name] = df[brand_col_name].str.cat(discovered_brands_series, sep=', ').str.strip(', ').replace('', None)
            df[brand_col_name] = df[brand_col_name].apply(lambda x: ', '.join(sorted(list(set(e.strip() for e in x.split(', ') if e.strip())))) if pd.notnull(x) else None)
        else:
            brand_col_name = 'Brand'
            df[brand_col_name] = discovered_brands

        for col_name, data in new_facet_cols.items():
            df[col_name] = data
        df.drop(columns=['Discovered Facets'], inplace=True, errors='ignore')
        return df, brand_col_name

    highest_ranking_df, brand_col_name = _organize_facets(highest_ranking_df, explicit_facets_df)

    all_facet_cols = {col for col in potential_facet_cols if col in highest_ranking_df.columns}
    all_facet_cols.add('Derived Facets')
    newly_organized_cols = {col for col in [brand_col_name, 'Voltage', 'Power Source', 'Features'] if col in highest_ranking_df.columns and col is not None}
    all_facet_cols.update(newly_organized_cols)
    all_facet_cols.discard('Discovered Facets')

    def is_redundant(category, facet_val):
        if nlp is None or pd.isnull(category) or pd.isnull(facet_val):
            return False
        cat_str = str(category).lower().replace('-', ' ')
        cat_lemmas = {token.lemma_ for token in nlp(cat_str)}
        facet_str = str(facet_val).lower().replace('-', ' ')
        facet_lemmas = {token.lemma_ for token in nlp(facet_str)}
        return facet_lemmas.issubset(cat_lemmas)

    for col in all_facet_cols:
        if col in highest_ranking_df.columns and col != 'Category Mapping':
            highest_ranking_df[col] = highest_ranking_df.apply(
                lambda row: None if is_redundant(row['Category Mapping'], row[col]) else row[col],
                axis=1
            )

    highest_ranking_df.dropna(axis=1, how='all', inplace=True)

    grouping_cols = ['Category Mapping'] + sorted([col for col in all_facet_cols if col in highest_ranking_df.columns])
    for col in grouping_cols:
        if col not in highest_ranking_df.columns:
            highest_ranking_df[col] = None
    highest_ranking_df[grouping_cols] = highest_ranking_df[grouping_cols].fillna('')
    highest_ranking_df[internal_traffic_col] = pd.to_numeric(highest_ranking_df[internal_traffic_col], errors='coerce').fillna(0)

    agg_dict = {internal_traffic_col: 'sum'}
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

    matrix_df = matrix_df.rename(columns={
        internal_traffic_col: 'Monthly Organic Traffic',
        internal_volume_col: 'Total Monthly Google Searches',
        'On-Site Searches': 'Total On-Site Searches'
    })

    matrix_df.sort_values('Monthly Organic Traffic', ascending=False, inplace=True)
    for col in ['Monthly Organic Traffic', 'Total Monthly Google Searches', 'Total On-Site Searches']:
        if col in matrix_df.columns:
            matrix_df[col] = matrix_df[col].astype(int)

    final_cols = [col for col in grouping_cols if col in matrix_df.columns] + ['Monthly Organic Traffic']
    if 'Total Monthly Google Searches' in matrix_df.columns:
        final_cols.append('Total Monthly Google Searches')
    if 'Total On-Site Searches' in matrix_df.columns:
        final_cols.append('Total On-Site Searches')
    matrix_df = matrix_df[final_cols + ['KeywordDetails']]

    facet_potential_report_raw = []
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

        melted_df = highest_ranking_df.melt(
            id_vars=id_vars,
            value_vars=facet_cols,
            var_name='Facet Type',
            value_name='Facet Value'
        )
        melted_df.dropna(subset=['Facet Value'], inplace=True)
        melted_df = melted_df[melted_df['Facet Value'] != '']
        if not melted_df.empty:
            value_agg_ops = {col: 'sum' for col in metric_cols}
            value_agg_ops[internal_keyword_col] = pd.Series.nunique
            value_level_df = melted_df.groupby(['Category Mapping', 'Facet Type', 'Facet Value'], as_index=False).agg(value_agg_ops)
            value_level_df = value_level_df.rename(columns={
                internal_traffic_col: 'Monthly Organic Traffic',
                internal_volume_col: 'Total Monthly Google Searches',
                'On-Site Searches': 'Total On-Site Searches',
                internal_keyword_col: 'Keyword Count'
            })
            parent_cols = ['Category Mapping', 'Facet Type']
            parent_agg_cols = [col for col in ['Monthly Organic Traffic', 'Total Monthly Google Searches', 'Total On-Site Searches', 'Keyword Count'] if col in value_level_df.columns]
            parent_level_df = value_level_df.groupby(parent_cols, as_index=False)[parent_agg_cols].sum()

            from sklearn.preprocessing import MinMaxScaler
            master_weights = {
                'Monthly Organic Traffic': 0.34,
                'Total Monthly Google Searches': 0.33,
                'Total On-Site Searches': 0.33
            }
            available_cols = [col for col in master_weights.keys() if col in parent_level_df.columns and not parent_level_df[col].isnull().all()]
            if available_cols and len(available_cols) > 0:
                total_weight_available = sum(master_weights[col] for col in available_cols)
                dynamic_weights = {col: master_weights[col] / total_weight_available for col in available_cols}
                scaler = MinMaxScaler()
                normalized_data = scaler.fit_transform(parent_level_df[available_cols])
                normalized_df = pd.DataFrame(normalized_data, columns=available_cols, index=parent_level_df.index)
                score = pd.Series(0, index=parent_level_df.index, dtype=float)
                for col, weight in dynamic_weights.items():
                    score += normalized_df[col] * weight
                parent_level_df['Facet Value Score'] = (score * 100).round(0)
            details_series = value_level_df.groupby(parent_cols).apply(lambda g: g.sort_values('Monthly Organic Traffic', ascending=False).to_dict('records'))
            details_series.name = 'FacetValueDetails'
            final_report_df = parent_level_df.set_index(parent_cols).join(details_series).reset_index()
            facet_potential_report_raw = final_report_df.to_dict(orient='records')

    matrix_df.replace({pd.NA: None, np.nan: None, '': None}, inplace=True)
    
    # Debug: Check if KeywordDetails are being populated
    sample_row = matrix_df.iloc[0] if not matrix_df.empty else None
    if sample_row is not None and 'KeywordDetails' in sample_row:
        print(f"Debug: Sample row has {len(sample_row['KeywordDetails'])} KeywordDetails")
        if len(sample_row['KeywordDetails']) > 0:
            print(f"Debug: First KeywordDetail sample: {sample_row['KeywordDetails'][0]}")
    
    return {
        "matrix_report": matrix_df.to_dict(orient='records'),
        "facet_potential_report": facet_potential_report_raw
    }