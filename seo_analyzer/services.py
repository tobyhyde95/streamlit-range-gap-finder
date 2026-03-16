# seo_analyzer/services.py
"""
Orchestration module — coordinates the full analysis pipeline.

Pipeline:
  Step 1: Data ingestion, de-duplication, stock classification (FR2)
  Step 2: NLP semantic clustering on "Not Stocked" queries (FR3)
  Step 3: Opportunity Scoring with configurable 60/40 formula (FR4)
  Step 4: Competitive context for top 20 groups (FR5)
  Step 5: Report generation
"""

import json

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

from . import analysis
from . import data_loader
from . import market_share_analysis as market
from . import report_generator as reports


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


def run_full_analysis(
    our_file_path,
    competitor_file_paths,
    onsite_file_path,
    options_str,
    progress_reporter=None,
    catalogue_file_path=None,
):
    """
    Run the complete analysis pipeline.

    Args:
        our_file_path: Path to domain CSV (Ahrefs export)
        competitor_file_paths: List of paths to competitor CSVs
        onsite_file_path: Path to GA4 on-site search CSV (optional)
        options_str: JSON string with column mapping and lens configuration
        progress_reporter: Callback for progress updates
        catalogue_file_path: Path to Toolstation product catalogue CSV (optional)
    """

    def report(message, current, total):
        if progress_reporter:
            progress_reporter(message, current, total)

    total_steps = 5

    # --- Step 0: Parse options ---
    report("Parsing and validating inputs...", 1, total_steps)
    try:
        options = json.loads(options_str)
        print(f"Column mapping options: {options['columnMap']}")
        internal_keyword_col = options['columnMap']['keywordCol'].replace(' ', '').replace('_', '')
        internal_position_col = options['columnMap']['positionCol'].replace(' ', '').replace('_', '')
        internal_url_col_name = options['columnMap']['urlCol'].replace(' ', '').replace('_', '')
        internal_volume_col = options['columnMap'].get('volumeCol', '').replace(' ', '').replace('_', '')
        internal_traffic_col = options['columnMap'].get('trafficCol', '').replace(' ', '').replace('_', '')
        onsite_date_range = options.get('onsiteDateRange', '')
        excluded_keywords = options.get('excludedKeywords', [])
        lenses_to_run = options.get('lensesToRun', {})
        rank_from = options.get('rankFrom')
        rank_to = options.get('rankTo')

        print(f"Normalized column names:")
        print(f"  keyword: '{internal_keyword_col}'")
        print(f"  position: '{internal_position_col}'")
        print(f"  url: '{internal_url_col_name}'")
        print(f"  volume: '{internal_volume_col}'")
        print(f"  traffic: '{internal_traffic_col}'")

    except (json.JSONDecodeError, KeyError) as e:
        raise ValueError(f"Invalid or missing options provided in request: {e}")

    # Initialize empty report containers
    keyword_gap_report_raw, topic_gap_report_raw, core_topic_gap_report_raw = [], [], []
    topic_keyword_map_by_topicid, core_topic_keyword_map_by_topicid = {}, {}
    keyword_threats_report_raw, topic_threats_report_raw, core_topic_threats_report_raw = [], [], []
    topic_threats_keyword_map_by_topicid, core_topic_threats_keyword_map_by_topicid = {}, {}
    keyword_market_share_report_raw, group_market_share_report_raw, core_group_market_share_report_raw = [], [], []
    group_market_share_keyword_map, core_group_market_share_keyword_map = {}, {}
    category_overhaul_matrix_report_raw, facet_potential_report_raw = [], []
    product_opportunity_report_raw = []
    product_opportunity_keyword_map = {}

    # --- Step 1: Data ingestion and de-duplication (FR2) ---
    report("Loading and de-duplicating data...", 1, total_steps)

    our_df, our_domain = data_loader.load_our_dataframe(
        our_file_path=our_file_path,
        internal_keyword_col=internal_keyword_col,
        internal_position_col=internal_position_col,
        internal_url_col_name=internal_url_col_name,
    )

    competitor_dfs, competitor_domains = data_loader.load_competitor_dataframes(
        competitor_file_paths=competitor_file_paths,
        internal_keyword_col=internal_keyword_col,
        internal_url_col_name=internal_url_col_name,
        our_domain=our_domain,
    )

    master_df = data_loader.build_master_dataframe(our_df, competitor_dfs)

    # Coerce numeric columns
    master_df = data_loader.coerce_numeric_columns(
        master_df,
        [internal_position_col, internal_volume_col, internal_traffic_col]
    )

    # Apply pre-filters
    master_df = data_loader.apply_pre_filters(
        master_df=master_df,
        excluded_keywords=excluded_keywords,
        rank_from=rank_from,
        rank_to=rank_to,
        internal_keyword_col=internal_keyword_col,
        internal_position_col=internal_position_col,
    )

    # De-duplicate queries across all sources (FR2)
    # Keep all source records for gap analysis but track unique queries
    all_unique_queries = master_df[internal_keyword_col].dropna().unique()
    print(f"Total unique queries after de-duplication: {len(all_unique_queries)}")

    # Load on-site search data (GA4)
    onsite_df, has_onsite_data = data_loader.load_onsite_data(onsite_file_path)

    # --- Step 1b: Stock classification (FR2) ---
    has_catalogue = False
    if catalogue_file_path:
        report("Classifying stock status against product catalogue...", 1, total_steps)
        try:
            from . import stock_classifier
            catalogue_df = stock_classifier.load_product_catalogue(catalogue_file_path)
            master_df = stock_classifier.classify_queries(
                master_df, internal_keyword_col, catalogue_df
            )
            has_catalogue = True
            print(f"Stock classification complete. "
                  f"Stocked: {(master_df['Stock Status'] == 'Stocked').sum()}, "
                  f"Not Stocked: {(master_df['Stock Status'] == 'Not Stocked').sum()}")
        except Exception as e:
            print(f"Warning: Stock classification failed: {e}. Proceeding without.")
            master_df['Stock Status'] = 'Not Stocked'
    else:
        master_df['Stock Status'] = 'Not Stocked'

    # --- Step 2: Semantic clustering (FR3) ---
    needs_clustering = any([
        lenses_to_run.get('content_gaps'),
        lenses_to_run.get('competitive_opportunities'),
        lenses_to_run.get('market_share'),
    ])

    topic_names = {}
    if needs_clustering:
        report("Performing NLP semantic clustering...", 2, total_steps)

        # Only cluster "Not Stocked" queries (FR2 → FR3 handoff)
        if has_catalogue:
            clustering_df = master_df[master_df['Stock Status'] == 'Not Stocked'].copy()
            print(f"Clustering {len(clustering_df)} 'Not Stocked' queries (excluded {(master_df['Stock Status'] == 'Stocked').sum()} stocked).")
        else:
            clustering_df = master_df.copy()

        clustering_df = clustering_df.dropna(subset=[internal_keyword_col]).copy()

        if not clustering_df.empty:
            topic_ids = analysis.perform_topic_clustering(clustering_df, internal_keyword_col)

            if topic_ids is not None:
                clustering_df['TopicID'] = topic_ids

                # Generate descriptive topic names
                topic_names = analysis.generate_topic_names(
                    clustering_df, internal_keyword_col, 'TopicID',
                    volume_col=internal_volume_col if internal_volume_col in clustering_df.columns else None
                )

                # Map TopicIDs and names back to full master_df
                kw_to_topic = clustering_df.drop_duplicates(subset=[internal_keyword_col]).set_index(internal_keyword_col)['TopicID']
                master_df['TopicID'] = master_df[internal_keyword_col].map(kw_to_topic)

                # Stocked items get TopicID = -2 (distinct from noise)
                if has_catalogue:
                    master_df.loc[master_df['Stock Status'] == 'Stocked', 'TopicID'] = -2

                # Fill remaining NaN TopicIDs (shouldn't happen but safety)
                master_df['TopicID'] = master_df['TopicID'].fillna(-1)
            else:
                master_df['TopicID'] = -1
        else:
            master_df['TopicID'] = -1

        master_df['Keyword Group'] = master_df['TopicID'].map(topic_names).fillna('Uncategorized')

        # --- Step 3: Opportunity Scoring (FR4) ---
        report("Calculating opportunity scores...", 3, total_steps)

        # Merge on-site search data for scoring
        if has_onsite_data:
            unique_kw_df = master_df.drop_duplicates(subset=[internal_keyword_col]).copy()
            unique_kw_df['lower_keyword'] = unique_kw_df[internal_keyword_col].str.lower()
            unique_kw_df = pd.merge(unique_kw_df, onsite_df, left_on='lower_keyword', right_on='keyword', how='left')
            onsite_map = unique_kw_df.set_index(internal_keyword_col)['searches'].fillna(0)
            master_df['On-Site Searches'] = master_df[internal_keyword_col].map(onsite_map).fillna(0)
        else:
            master_df['On-Site Searches'] = 0

        # Build Product Opportunity Group report (for Not Stocked only)
        not_stocked_df = master_df[master_df['TopicID'] >= 0].copy()

        if not not_stocked_df.empty:
            opp_report_df, product_opportunity_keyword_map = reports.create_product_opportunity_report(
                df=not_stocked_df,
                keyword_col=internal_keyword_col,
                topic_col='TopicID',
                topic_names=topic_names,
                volume_col=internal_volume_col,
                internal_searches_col='On-Site Searches',
                traffic_col=internal_traffic_col,
                position_col=internal_position_col,
                url_col=internal_url_col_name,
                has_onsite_data=has_onsite_data,
            )
            opp_report_df.replace({np.nan: None}, inplace=True)
            product_opportunity_report_raw = opp_report_df.to_dict(orient='records')

        # Also compute per-keyword opportunity scores for legacy reports
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
            prelim_keywords_df.rename(columns={'searches': 'On-Site Searches_kw'}, inplace=True)

            # Use the new 60/40 formula for keyword-level scores too
            if internal_volume_col and internal_volume_col in prelim_keywords_df.columns:
                prelim_keywords_df['Opportunity Score'] = reports.calculate_opportunity_scores(
                    prelim_keywords_df,
                    external_vol_col=internal_volume_col,
                    internal_vol_col='On-Site Searches_kw',
                )
            else:
                prelim_keywords_df['Opportunity Score'] = 0

    else:
        report("Skipping semantic clustering as per user selection...", 2, total_steps)
        master_df['TopicID'] = -1
        master_df['Keyword Group'] = 'N/A'
        master_df['On-Site Searches'] = 0

    # --- Step 4: Generate lens-specific reports ---
    report("Generating analysis reports...", 4, total_steps)
    our_ranking_keywords = master_df[master_df['Source'] == our_domain][internal_keyword_col].unique()

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
                keyword_gap_agg['On-Site Searches'] = keyword_gap_agg['On-Site Searches'].fillna(0).astype(int)

                if 'Opportunity Score' in locals().get('prelim_keywords_df', pd.DataFrame()).columns:
                    scores_to_merge = prelim_keywords_df[['lower_keyword', 'Opportunity Score']]
                    keyword_gap_agg = pd.merge(keyword_gap_agg, scores_to_merge, on='lower_keyword', how='left')

                keyword_gap_agg.drop(columns=['lower_keyword', 'keyword'], inplace=True, errors='ignore')
            else:
                keyword_gap_agg['On-Site Searches'] = 0

            # Add stock status to keyword-level report
            if has_catalogue:
                stock_map = master_df.drop_duplicates(subset=[internal_keyword_col]).set_index(internal_keyword_col)['Stock Status']
                keyword_gap_agg['Stock Status'] = keyword_gap_agg[internal_keyword_col].map(stock_map).fillna('Not Stocked')

            keyword_gap_agg.replace({np.nan: None}, inplace=True)
            keyword_gap_report_raw = keyword_gap_agg.rename(columns={internal_keyword_col: 'Keyword'}).to_dict(orient='records')

            for scope in ['full', 'core']:
                report_df = competitor_only_df if scope == 'full' else competitor_only_df[competitor_only_df[internal_position_col] <= 20]
                if report_df.empty:
                    if scope == 'full':
                        topic_gap_report_raw, topic_keyword_map_by_topicid = [], {}
                    else:
                        core_topic_gap_report_raw, core_topic_keyword_map_by_topicid = [], {}
                    continue

                topic_agg_df, topic_map = reports.create_topic_report(
                    df_for_topic_report_input=report_df,
                    full_onsite_df=onsite_df,
                    internal_keyword_col=internal_keyword_col,
                    internal_position_col=internal_position_col,
                    internal_volume_col=internal_volume_col,
                    internal_traffic_col=internal_traffic_col,
                    topic_names=topic_names,
                    has_onsite_data=has_onsite_data,
                )

                if has_onsite_data and not topic_agg_df.empty:
                    topic_agg_df = reports.add_opportunity_scores_if_applicable(topic_agg_df, has_onsite_data)

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

    if lenses_to_run.get('competitive_opportunities'):
        shared_keywords_df = master_df[master_df[internal_keyword_col].isin(our_ranking_keywords)].copy()
        if not shared_keywords_df.empty:
            our_data = shared_keywords_df[shared_keywords_df['Source'] == our_domain]
            comp_data = shared_keywords_df[shared_keywords_df['Source'] != our_domain]

            if not comp_data.empty:
                best_comp_data = comp_data.loc[comp_data.groupby(internal_keyword_col)[internal_position_col].idxmin()]

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

                    leakage_df['MonthlyTrafficGrowthOpportunity'] = leakage_df[f'{internal_traffic_col}_Comp'] - leakage_df[f'{internal_traffic_col}_Our']

                    final_cols_map = {
                        internal_keyword_col: 'Keyword', f'{internal_volume_col}_Our': 'Monthly Google Searches', f'{internal_position_col}_Our': 'Our Rank',
                        f'{internal_url_col_name}_Our': 'Our URL', f'{internal_traffic_col}_Our': 'Our Monthly Organic Traffic', 'Source_Comp': 'Best Competitor',
                        f'{internal_position_col}_Comp': 'Best Competitor Rank', f'{internal_url_col_name}_Comp': 'Best Competitor URL',
                        f'{internal_traffic_col}_Comp': 'Best Competitor Monthly Organic Traffic', 'MonthlyTrafficGrowthOpportunity': 'Monthly Traffic Growth Opportunity'
                    }

                    filtered_final_cols_map = {k: v for k, v in final_cols_map.items() if k in leakage_df.columns}
                    keyword_threats_df = leakage_df[list(filtered_final_cols_map.keys())].rename(columns=filtered_final_cols_map)

                    keyword_threats_df.replace({np.nan: None}, inplace=True)
                    keyword_threats_report_raw = keyword_threats_df.to_dict(orient='records')

                    topic_threats_report_raw, topic_threats_keyword_map_by_topicid = reports.create_threat_topic_report(
                        df_for_threats_input=keyword_threats_df,
                        master_df=master_df,
                        internal_keyword_col=internal_keyword_col,
                        topic_names=topic_names
                    )

                    core_leakage_df = keyword_threats_df.dropna(subset=['Best Competitor Rank'])
                    core_leakage_df = core_leakage_df[core_leakage_df['Best Competitor Rank'] <= 10].copy()
                    core_topic_threats_report_raw, core_topic_threats_keyword_map_by_topicid = reports.create_threat_topic_report(
                        df_for_threats_input=core_leakage_df,
                        master_df=master_df,
                        internal_keyword_col=internal_keyword_col,
                        topic_names=topic_names
                    )

    if lenses_to_run.get('market_share') and internal_traffic_col:
        keyword_market_share_report_raw = market._calculate_keyword_market_share(master_df, internal_keyword_col, 'Source', internal_traffic_col)

        group_market_share_df = market._calculate_group_market_share(master_df, 'Keyword Group', 'Source', internal_traffic_col)
        if not group_market_share_df.empty:
            group_market_share_keyword_map = master_df.groupby('Keyword Group')[internal_keyword_col].unique().apply(list).to_dict()
            group_market_share_df['Keyword Count'] = group_market_share_df['Keyword Group'].map(lambda g: len(group_market_share_keyword_map.get(g, [])))
            group_market_share_df.replace({np.nan: None}, inplace=True)
            group_market_share_report_raw = group_market_share_df.to_dict(orient='records')

        core_master_df = master_df[master_df[internal_position_col] <= 20].copy()
        core_group_market_share_df = market._calculate_group_market_share(core_master_df, 'Keyword Group', 'Source', internal_traffic_col)
        if not core_group_market_share_df.empty:
            core_group_market_share_keyword_map = core_master_df.groupby('Keyword Group')[internal_keyword_col].unique().apply(list).to_dict()
            core_group_market_share_df['Keyword Count'] = core_group_market_share_df['Keyword Group'].map(lambda g: len(core_group_market_share_keyword_map.get(g, [])))
            core_group_market_share_df.replace({np.nan: None}, inplace=True)
            core_group_market_share_report_raw = core_group_market_share_df.to_dict(orient='records')

    report("Analysis complete.", 5, total_steps)

    return {
        # New Product Opportunity Group report
        "productOpportunityReport": product_opportunity_report_raw,
        "productOpportunityKeywordMap": product_opportunity_keyword_map,
        # Legacy reports (content gaps)
        "keywordGapReport": keyword_gap_report_raw,
        "topicGapReport": topic_gap_report_raw,
        "coreTopicGapReport": core_topic_gap_report_raw,
        "topicKeywordMap": topic_keyword_map_by_topicid,
        "coreTopicKeywordMap": core_topic_keyword_map_by_topicid,
        # Competitive opportunities
        "keywordThreatsReport": keyword_threats_report_raw,
        "topicThreatsReport": topic_threats_report_raw,
        "coreTopicThreatsReport": core_topic_threats_report_raw,
        "topicThreatsKeywordMap": topic_threats_keyword_map_by_topicid,
        "coreTopicThreatsKeywordMap": core_topic_threats_keyword_map_by_topicid,
        # Market share
        "keywordMarketShareReport": keyword_market_share_report_raw,
        "groupMarketShareReport": group_market_share_report_raw,
        "coreGroupMarketShareReport": core_group_market_share_report_raw,
        "groupMarketShareKeywordMap": group_market_share_keyword_map,
        "coreGroupMarketShareKeywordMap": core_group_market_share_keyword_map,
        # Legacy
        "categoryOverhaulMatrixReport": category_overhaul_matrix_report_raw,
        "facetPotentialReport": facet_potential_report_raw,
        # Metadata
        "hasOnsiteData": has_onsite_data,
        "hasCatalogue": has_catalogue,
        "columnMap": options['columnMap'],
        "ourDomain": our_domain,
        "competitorDomains": competitor_domains,
        "onsiteDateRange": onsite_date_range,
    }
