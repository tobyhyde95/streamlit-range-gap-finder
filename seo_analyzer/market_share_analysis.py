import numpy as np
import pandas as pd


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


