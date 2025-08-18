# utils.py
from urllib.parse import urlparse


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