import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler


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
    if not has_onsite_data or topic_agg_df.empty:
        return topic_agg_df
    score_cols_agg = ['TotalMonthlyGoogleSearches', 'TotalCompetitorMonthlyOrganicTraffic', 'OnSiteSearches']
    valid_score_cols_agg = [col for col in score_cols_agg if col in topic_agg_df.columns]
    if len(valid_score_cols_agg) > 0:
        scaler_agg = MinMaxScaler()
        topic_agg_df[valid_score_cols_agg] = topic_agg_df[valid_score_cols_agg].fillna(0)
        normalized_data_agg = scaler_agg.fit_transform(topic_agg_df[valid_score_cols_agg])
        normalized_df_agg = pd.DataFrame(normalized_data_agg, columns=valid_score_cols_agg, index=topic_agg_df.index)
        weights_agg = {'TotalMonthlyGoogleSearches': 0.20, 'TotalCompetitorMonthlyOrganicTraffic': 0.40, 'OnSiteSearches': 0.40}
        topic_agg_df['Opportunity Score'] = sum(normalized_df_agg.get(col, 0) * weights_agg.get(col, 0) for col in valid_score_cols_agg) * 100
        topic_agg_df['Opportunity Score'] = topic_agg_df['Opportunity Score'].round(0)
    return topic_agg_df


