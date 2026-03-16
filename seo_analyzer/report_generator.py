"""
Report Generator — produces Product Opportunity Group reports.

Scoring formula (FR4):
  Opportunity Score = (Normalised External Volume × W_ext) + (Normalised Internal Volume × W_int)
  Where W_ext and W_int are loaded from scoring_config.json (default 0.6 / 0.4).

Output columns per Product Opportunity Group (NFR1/NFR2):
  - Product Opportunity Group ID
  - Group Label (most descriptive/representative query)
  - Opportunity Score (0–100)
  - Ahrefs Vol (aggregated external volume)
  - Internal Searches (aggregated GA4 on-site searches)
  - Keyword Variant Count
  - Top Competitor URL (for top 20 groups) (FR5)
  - Stock Status Confirmation
"""

import json
import os

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler


_config_path = os.path.join(os.path.dirname(__file__), "scoring_config.json")


def _load_scoring_weights():
    """Load opportunity score weights from the parameter file."""
    try:
        with open(_config_path, "r") as f:
            config = json.load(f)
        weights = config.get("opportunity_score_weights", {})
        return (
            weights.get("external_volume_weight", 0.6),
            weights.get("internal_volume_weight", 0.4),
        )
    except (FileNotFoundError, json.JSONDecodeError):
        return 0.6, 0.4


def _load_output_config():
    """Load output configuration (top N for competitor context, color thresholds)."""
    try:
        with open(_config_path, "r") as f:
            config = json.load(f)
        return config.get("output", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def calculate_opportunity_scores(
    df: pd.DataFrame,
    external_vol_col: str,
    internal_vol_col: str,
) -> pd.Series:
    """
    Calculate Opportunity Score (0–100) using the configurable weighted formula.

    Formula: (Normalised_External × W_ext + Normalised_Internal × W_int) × 100

    AC-01: Given external vol = 100, internal vol = 50,
           when 60/40 applied → score = (1.0 × 0.6 + 0.5 × 0.4) × 100 = 80
    """
    w_ext, w_int = _load_scoring_weights()

    ext_values = df[external_vol_col].fillna(0).values.reshape(-1, 1) if external_vol_col in df.columns else np.zeros((len(df), 1))
    int_values = df[internal_vol_col].fillna(0).values.reshape(-1, 1) if internal_vol_col in df.columns else np.zeros((len(df), 1))

    # Normalise each to 0–100 scale independently
    scaler_ext = MinMaxScaler(feature_range=(0, 100))
    scaler_int = MinMaxScaler(feature_range=(0, 100))

    if ext_values.max() > 0:
        norm_ext = scaler_ext.fit_transform(ext_values).flatten()
    else:
        norm_ext = np.zeros(len(df))

    if int_values.max() > 0:
        norm_int = scaler_int.fit_transform(int_values).flatten()
    else:
        norm_int = np.zeros(len(df))

    # Apply weighted formula
    scores = (norm_ext * w_ext) + (norm_int * w_int)

    return pd.Series(scores, index=df.index).round(0).astype(int)


def create_product_opportunity_report(
    df: pd.DataFrame,
    keyword_col: str,
    topic_col: str,
    topic_names: dict,
    volume_col: str,
    internal_searches_col: str,
    traffic_col: str,
    position_col: str,
    url_col: str,
    has_onsite_data: bool,
) -> tuple:
    """
    Create the Product Opportunity Group report (FR3/FR4/FR5).

    Returns:
        (report_df, keyword_map)
        report_df — one row per Product Opportunity Group, sorted by Opportunity Score desc
        keyword_map — dict mapping TopicID → list of constituent keywords
    """
    if df.empty:
        return pd.DataFrame(), {}

    output_config = _load_output_config()
    top_n_competitor = output_config.get("top_n_competitor_context", 20)

    # Build keyword map: TopicID → list of keywords
    keyword_map = (
        df.groupby(topic_col)[keyword_col]
        .unique()
        .apply(list)
        .to_dict()
    )

    # Aggregation per Product Opportunity Group
    agg_ops = {
        'Keyword Variant Count': (keyword_col, 'nunique'),
    }

    if volume_col and volume_col in df.columns:
        agg_ops['Ahrefs Vol'] = (volume_col, 'sum')

    if internal_searches_col and internal_searches_col in df.columns:
        agg_ops['Internal Searches'] = (internal_searches_col, 'sum')

    if traffic_col and traffic_col in df.columns:
        agg_ops['Total Competitor Traffic'] = (traffic_col, 'sum')

    if position_col and position_col in df.columns:
        agg_ops['Competitor Avg Rank'] = (position_col, 'mean')

    report_df = df.groupby(topic_col).agg(**agg_ops).reset_index()

    # Map topic names
    report_df['Group Label'] = report_df[topic_col].map(topic_names).fillna('Uncategorized')

    # Rename TopicID to Product Opportunity Group ID
    report_df = report_df.rename(columns={topic_col: 'Product Opportunity Group ID'})

    # Calculate Opportunity Score
    ext_col = 'Ahrefs Vol' if 'Ahrefs Vol' in report_df.columns else None
    int_col = 'Internal Searches' if 'Internal Searches' in report_df.columns else None

    if ext_col or int_col:
        report_df['Opportunity Score'] = calculate_opportunity_scores(
            report_df,
            external_vol_col=ext_col or '_dummy_',
            internal_vol_col=int_col or '_dummy_',
        )
    else:
        report_df['Opportunity Score'] = 0

    # Round numeric columns
    if 'Competitor Avg Rank' in report_df.columns:
        report_df['Competitor Avg Rank'] = report_df['Competitor Avg Rank'].round(2)

    # Sort by Opportunity Score descending (NFR1)
    report_df = report_df.sort_values('Opportunity Score', ascending=False).reset_index(drop=True)

    # FR5: Competitive context for top N groups
    report_df['Top Competitor URL'] = None
    if url_col and url_col in df.columns and position_col and position_col in df.columns:
        top_group_ids = report_df.head(top_n_competitor)['Product Opportunity Group ID'].tolist()
        for gid in top_group_ids:
            group_keywords = keyword_map.get(gid, [])
            if not group_keywords:
                continue
            group_rows = df[df[keyword_col].isin(group_keywords)]
            if group_rows.empty:
                continue
            # Best ranking competitor URL
            best_row = group_rows.loc[group_rows[position_col].idxmin()]
            report_df.loc[
                report_df['Product Opportunity Group ID'] == gid,
                'Top Competitor URL'
            ] = best_row[url_col]

    # Stock status confirmation
    report_df['Stock Status'] = 'Not Stocked'

    # Constituent data display (NFR2 — Transparency)
    ahrefs_vals = report_df.get('Ahrefs Vol', pd.Series([0] * len(report_df)))
    internal_vals = report_df.get('Internal Searches', pd.Series([0] * len(report_df)))
    report_df['Constituent Data'] = (
        'Ahrefs Vol: ' + ahrefs_vals.fillna(0).astype(int).astype(str) +
        ' | Internal Searches: ' + internal_vals.fillna(0).astype(int).astype(str)
    )

    # Reorder columns for output
    column_order = [
        'Product Opportunity Group ID',
        'Group Label',
        'Opportunity Score',
        'Constituent Data',
        'Ahrefs Vol',
        'Internal Searches',
        'Keyword Variant Count',
        'Top Competitor URL',
        'Stock Status',
        'Competitor Avg Rank',
        'Total Competitor Traffic',
    ]
    column_order = [c for c in column_order if c in report_df.columns]
    report_df = report_df[column_order]

    report_df.replace({np.nan: None}, inplace=True)

    return report_df, keyword_map


def create_topic_report(
    df_for_topic_report_input: pd.DataFrame,
    full_onsite_df: pd.DataFrame,
    internal_keyword_col: str,
    internal_position_col: str,
    internal_volume_col: str,
    internal_traffic_col: str,
    topic_names: dict,
    has_onsite_data: bool
):
    """Legacy topic report — wraps the new Product Opportunity Group report."""
    if df_for_topic_report_input.empty:
        return pd.DataFrame(), {}

    df_for_topic_report_cleaned = df_for_topic_report_input.dropna(subset=[internal_keyword_col]).copy()
    if df_for_topic_report_cleaned.empty:
        return pd.DataFrame(), {}

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
    if not internal_volume_col:
        agg_ops.pop('TotalMonthlyGoogleSearches', None)
    if not internal_traffic_col:
        agg_ops.pop('TotalCompetitorMonthlyOrganicTraffic', None)

    topic_agg_by_topicid = df_for_topic_report_cleaned.groupby('TopicID').agg(**agg_ops).reset_index()
    topic_agg_by_topicid['Keyword Group'] = topic_agg_by_topicid['TopicID'].map(topic_names).fillna('Uncategorized')

    return topic_agg_by_topicid, topic_keywords_map_by_topicid_local


def create_threat_topic_report(
    df_for_threats_input: pd.DataFrame,
    master_df: pd.DataFrame,
    internal_keyword_col: str,
    topic_names: dict
):
    if df_for_threats_input.empty:
        return [], {}

    master_keyword_group_map = master_df.drop_duplicates(subset=[internal_keyword_col])[[internal_keyword_col, 'TopicID', 'Keyword Group']].copy()
    df_with_groups = pd.merge(df_for_threats_input, master_keyword_group_map, left_on='Keyword', right_on=internal_keyword_col, how='left')

    keyword_map = df_with_groups.groupby('TopicID')['Keyword'].unique().apply(list).to_dict()
    agg_dict = {
        'AvgOurRank': ('Our Rank', 'mean'),
        'AvgBestCompetitorRank': ('Best Competitor Rank', 'mean'),
        'TotalOurMonthlyTraffic': ('Our Monthly Organic Traffic', 'sum'),
        'TotalBestCompetitorMonthlyTraffic': ('Best Competitor Monthly Organic Traffic', 'sum'),
        'TotalMonthlyTrafficGrowthOpportunity': ('Monthly Traffic Growth Opportunity', 'sum'),
        'KeywordCount': ('Keyword', 'nunique')
    }
    if 'Monthly Google Searches' in df_for_threats_input.columns:
        agg_dict['TotalMonthlyGoogleSearches'] = ('Monthly Google Searches', 'sum')

    topic_threats_agg = df_with_groups.groupby('TopicID').agg(**agg_dict).reset_index()
    topic_threats_agg['Keyword Group'] = topic_threats_agg['TopicID'].map(topic_names).fillna('Uncategorized')

    rename_dict = {
        'AvgOurRank': 'Avg Our Rank',
        'AvgBestCompetitorRank': 'Avg Best Competitor Rank',
        'TotalOurMonthlyTraffic': 'Total Our Monthly Traffic',
        'TotalBestCompetitorMonthlyTraffic': 'Total Best Competitor Monthly Traffic',
        'TotalMonthlyTrafficGrowthOpportunity': 'Total Monthly Traffic Growth Opportunity',
        'TotalMonthlyGoogleSearches': 'Total Monthly Google Searches',
        'KeywordCount': 'Keyword Count'
    }
    topic_threats_agg = topic_threats_agg.rename(columns=rename_dict)

    if 'Avg Our Rank' in topic_threats_agg.columns:
        topic_threats_agg['Avg Our Rank'] = topic_threats_agg['Avg Our Rank'].round(2)
    if 'Avg Best Competitor Rank' in topic_threats_agg.columns:
        topic_threats_agg['Avg Best Competitor Rank'] = topic_threats_agg['Avg Best Competitor Rank'].round(2)

    topic_threats_agg.replace({np.nan: None}, inplace=True)
    return topic_threats_agg.to_dict(orient='records'), keyword_map


def add_opportunity_scores_if_applicable(
    topic_agg_df: pd.DataFrame,
    has_onsite_data: bool
) -> pd.DataFrame:
    """Add opportunity scores to a topic aggregation using the configurable formula."""
    if not has_onsite_data or topic_agg_df.empty:
        return topic_agg_df

    ext_col = 'TotalMonthlyGoogleSearches'
    int_col = 'OnSiteSearches'

    if ext_col in topic_agg_df.columns or int_col in topic_agg_df.columns:
        topic_agg_df['Opportunity Score'] = calculate_opportunity_scores(
            topic_agg_df,
            external_vol_col=ext_col,
            internal_vol_col=int_col,
        )

    return topic_agg_df
