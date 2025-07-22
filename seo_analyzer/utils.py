# utils.py
import pandas as pd
import io
from urllib.parse import urlparse

def read_csv_with_encoding_fallback(file_stream):
    """Reads a CSV file stream with a fallback to latin-1 encoding."""
    try:
        # Ensure the stream is at the beginning before reading
        file_stream.seek(0)
        file_content = file_stream.read()
        try:
            decoded_content = file_content.decode('UTF-8')
        except UnicodeDecodeError:
            decoded_content = file_content.decode('latin-1')
        
        df = pd.read_csv(io.StringIO(decoded_content))
        # Strip whitespace from column names for consistency
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return None

def get_domain_from_url(url_string):
    """Parses a URL string to extract the root domain."""
    if not isinstance(url_string, str): return None
    url_string = url_string.strip()
    if not url_string: return None
    try:
        if not url_string.startswith(('http://', 'https://')):
            url_string = 'https://' + url_string
        hostname = urlparse(url_string).hostname
        if hostname and hostname.startswith('www.'):
            return hostname[4:]
        return hostname
    except Exception:
        return None