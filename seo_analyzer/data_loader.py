import io
import re
import pandas as pd
from typing import List, Tuple, Optional

from . import utils


# Columns from raw exports that we consistently exclude at source
COLS_TO_EXCLUDE_AT_SOURCE = {
    'countrycode', 'location', 'entities', 'serpfeatures', 'kd', 'cpc', 'paidtraffic',
    'currenturlinside', 'updated', 'branded', 'local', 'navigational',
    'informational', 'commercial', 'transactional'
}


def read_csv_with_encoding_fallback(file_stream) -> Optional[pd.DataFrame]:
    """Reads a CSV file stream with fallback encoding and delimiter detection."""
    try:
        file_stream.seek(0)
        
        # First, try to read a sample to detect the delimiter
        sample_text = file_stream.read(1024).decode('utf-8', errors='ignore')
        file_stream.seek(0)
        
        # Count delimiters in the first few lines
        lines = sample_text.split('\n')[:3]
        comma_count = sum(line.count(',') for line in lines)
        tab_count = sum(line.count('\t') for line in lines)
        semicolon_count = sum(line.count(';') for line in lines)
        
        # Determine the most likely delimiter
        if tab_count > comma_count and tab_count > semicolon_count:
            delimiter = '\t'
        elif semicolon_count > comma_count:
            delimiter = ';'
        else:
            delimiter = ','
        
        print(f"Detected delimiter: '{delimiter}' (comma: {comma_count}, tab: {tab_count}, semicolon: {semicolon_count})")
        
        # Try different encodings and delimiters
        encodings = ['UTF-8', 'UTF-16', 'latin-1', 'cp1252']
        
        for encoding in encodings:
            try:
                file_stream.seek(0)
                # Handle BOM and encoding issues
                df = pd.read_csv(file_stream, encoding=encoding, delimiter=delimiter, on_bad_lines='skip')
                
                # Clean up column names - remove BOM and other artifacts
                df.columns = df.columns.str.strip()
                df.columns = df.columns.str.replace('ÿþ"', '')  # Remove BOM
                df.columns = df.columns.str.replace('^"|"$', '', regex=True)  # Remove surrounding quotes
                
                # If all columns are unnamed, try reading with header=0 explicitly
                if all(col.startswith('Unnamed:') for col in df.columns):
                    print(f"All columns are unnamed with {encoding}, trying with explicit header")
                    file_stream.seek(0)
                    df = pd.read_csv(file_stream, encoding=encoding, delimiter=delimiter, header=0, on_bad_lines='skip')
                    df.columns = df.columns.str.strip()
                    df.columns = df.columns.str.replace('ÿþ"', '')  # Remove BOM
                    df.columns = df.columns.str.replace('^"|"$', '', regex=True)  # Remove surrounding quotes
                
                # If still all unnamed, try reading the raw file and parsing manually
                if all(col.startswith('Unnamed:') for col in df.columns):
                    print(f"Still all unnamed with {encoding}, trying manual parsing")
                    file_stream.seek(0)
                    raw_text = file_stream.read().decode(encoding, errors='ignore')
                    lines = raw_text.split('\n')
                    if len(lines) > 0:
                        # Parse the first line manually to get headers
                        header_line = lines[0]
                        headers = header_line.split(delimiter)
                        headers = [h.strip().replace('ÿþ"', '').replace('"', '') for h in headers]
                        print(f"Manual parsed headers: {headers}")
                        
                        # Read the data without header
                        file_stream.seek(0)
                        df = pd.read_csv(file_stream, encoding=encoding, delimiter=delimiter, header=None, skiprows=1, on_bad_lines='skip')
                        df.columns = headers
                
                print(f"Successfully read CSV with encoding: {encoding}, delimiter: '{delimiter}'")
                print(f"Columns after cleaning: {df.columns.tolist()}")
                return df
            except (UnicodeDecodeError, pd.errors.ParserError) as e:
                print(f"Failed with encoding {encoding}: {e}")
                continue
            except Exception as e:
                print(f"Unexpected error with encoding {encoding}: {e}")
                continue
        
        # If all encodings fail, try with different delimiters
        alternative_delimiters = [',', '\t', ';', '|']
        for alt_delimiter in alternative_delimiters:
            if alt_delimiter == delimiter:
                continue
            try:
                file_stream.seek(0)
                df = pd.read_csv(file_stream, encoding='UTF-8', delimiter=alt_delimiter, on_bad_lines='skip')
                df.columns = df.columns.str.strip()
                df.columns = df.columns.str.replace('ÿþ"', '')  # Remove BOM
                df.columns = df.columns.str.replace('^"|"$', '', regex=True)  # Remove surrounding quotes
                print(f"Successfully read CSV with alternative delimiter: '{alt_delimiter}'")
                return df
            except Exception as e:
                print(f"Failed with delimiter '{alt_delimiter}': {e}")
                continue
        
        print("All CSV parsing attempts failed")
        return None
        
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return None


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names by removing spaces/underscores to match internal mapping."""
    if df is None:
        return df
    original_cols = df.columns.tolist()
    rename_map = {col: col.replace(' ', '').replace('_', '') for col in original_cols}
    df = df.rename(columns=rename_map)
    # Deduplicate columns if any collisions occurred after normalization
    if df.columns.has_duplicates:
        df = df.groupby(level=0, axis=1).apply(lambda group: group.ffill(axis=1).bfill(axis=1).iloc[:, 0])
    return df


def _drop_unwanted_source_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        return df
    cols_to_drop = [col for col in df.columns if col.lower() in COLS_TO_EXCLUDE_AT_SOURCE]
    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)
    return df


def load_our_dataframe(
    our_file_path: str,
    internal_keyword_col: str,
    internal_position_col: str,
    internal_url_col_name: str,
) -> Tuple[pd.DataFrame, str]:
    """Load and preprocess the user's domain CSV, returning dataframe and detected domain."""
    with open(our_file_path, 'rb') as f:
        our_df = read_csv_with_encoding_fallback(f)
    if our_df is None:
        raise ValueError("Could not read your domain's CSV file.")

    print(f"Original columns: {our_df.columns.tolist()}")
    our_df = _normalize_columns(our_df)
    print(f"After normalization: {our_df.columns.tolist()}")
    our_df = _drop_unwanted_source_columns(our_df)
    print(f"After dropping unwanted columns: {our_df.columns.tolist()}")

    if internal_keyword_col in our_df.columns:
        our_df[internal_keyword_col] = our_df[internal_keyword_col].astype(str).str.strip().str.lower()

    required_internal_cols = {internal_keyword_col, internal_position_col, internal_url_col_name}
    print(f"Required columns: {required_internal_cols}")
    print(f"Available columns: {set(our_df.columns)}")
    missing_cols = required_internal_cols - set(our_df.columns)
    if missing_cols:
        print(f"Missing columns: {missing_cols}")
        raise ValueError(f"Your main file is missing required columns based on your mapping: {missing_cols}")

    our_domain = next((d for d in (utils.get_domain_from_url(url) for url in our_df[internal_url_col_name].head(10)) if d), None)
    if not our_domain:
        raise ValueError("Could not determine your domain from the URL column.")
    our_df['Source'] = our_domain

    return our_df, our_domain


def load_competitor_dataframes(
    competitor_file_paths: List[str],
    internal_keyword_col: str,
    internal_url_col_name: str,
    our_domain: str
) -> Tuple[List[pd.DataFrame], List[str]]:
    """Load, normalize and annotate competitor CSVs; returns list of dataframes and domains."""
    competitor_dfs: List[pd.DataFrame] = []
    competitor_domains: List[str] = []

    for path in competitor_file_paths:
        with open(path, 'rb') as f_stream:
            df = read_csv_with_encoding_fallback(f_stream)
        if df is None:
            continue
        df = _normalize_columns(df)
        df = _drop_unwanted_source_columns(df)
        if internal_keyword_col in df.columns:
            df[internal_keyword_col] = df[internal_keyword_col].astype(str).str.strip().str.lower()
        if internal_url_col_name in df.columns:
            comp_domain = next(
                (d for d in (utils.get_domain_from_url(url) for url in df[internal_url_col_name].head(10)) if d and d != our_domain),
                None
            )
            if comp_domain:
                df['Source'] = comp_domain
                competitor_domains.append(comp_domain)
                competitor_dfs.append(df)

    return competitor_dfs, competitor_domains


def build_master_dataframe(our_df: pd.DataFrame, competitor_dfs: List[pd.DataFrame]) -> pd.DataFrame:
    """Concatenate our and competitor dataframes into a single master dataframe."""
    all_dfs = [our_df] + competitor_dfs
    master_df = pd.concat(all_dfs, ignore_index=True)
    return master_df


def apply_pre_filters(
    master_df: pd.DataFrame,
    excluded_keywords: List[str],
    rank_from: Optional[int],
    rank_to: Optional[int],
    internal_keyword_col: str,
    internal_position_col: str
) -> pd.DataFrame:
    """Apply excluded keyword filtering and rank range filtering to the master dataframe."""
    if excluded_keywords:
        print(f"Excluding {len(excluded_keywords)} branded terms...")
        exclude_pattern = '|'.join([re.escape(kw) for kw in excluded_keywords])
        initial_rows = len(master_df)
        master_df = master_df[~master_df[internal_keyword_col].str.contains(exclude_pattern, case=False, na=False)]
        print(f"Removed {initial_rows - len(master_df)} rows containing branded keywords.")

    if rank_from or rank_to:
        initial_rows = len(master_df)
        master_df = master_df.dropna(subset=[internal_position_col]).copy()
        if rank_from is not None:
            try:
                master_df = master_df[master_df[internal_position_col] >= int(rank_from)]
            except (ValueError, TypeError):
                print(f"Warning: Invalid 'Ranking From' value '{rank_from}'.")
        if rank_to is not None:
            try:
                master_df = master_df[master_df[internal_position_col] <= int(rank_to)]
            except (ValueError, TypeError):
                print(f"Warning: Invalid 'Ranking To' value '{rank_to}'.")
        print(f"Filtered by rank. Removed {initial_rows - len(master_df)} rows.")

    return master_df


def load_onsite_data(onsite_file_path: Optional[str]) -> Tuple[Optional[pd.DataFrame], bool]:
    """Load and standardize onsite search data; returns dataframe and boolean flag."""
    if not onsite_file_path:
        return None, False
    with open(onsite_file_path, 'rb') as f:
        onsite_df_raw = read_csv_with_encoding_fallback(f)
    if onsite_df_raw is not None and len(onsite_df_raw.columns) >= 2:
        onsite_df_raw.columns = ['keyword', 'searches']
        onsite_df_raw['keyword'] = onsite_df_raw['keyword'].astype(str).str.strip().str.lower()
        onsite_df_raw['searches'] = pd.to_numeric(onsite_df_raw['searches'], errors='coerce').fillna(0).astype(int)
        onsite_df = onsite_df_raw.groupby('keyword')['searches'].sum().reset_index()
        return onsite_df, True
    return None, False


def coerce_numeric_columns(
    master_df: pd.DataFrame,
    numeric_cols: List[Optional[str]]
) -> pd.DataFrame:
    """Coerce the provided columns to numeric, ignoring missing ones."""
    for col in numeric_cols:
        if col and col in master_df.columns:
            master_df[col] = pd.to_numeric(master_df[col], errors='coerce')
    return master_df


