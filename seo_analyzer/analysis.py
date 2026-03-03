# seo_analyzer/analysis.py
import os
import tempfile
import pandas as pd
from sentence_transformers import SentenceTransformer
import hdbscan
from umap import UMAP
from joblib import Memory
from urllib.parse import urlparse

# --- 1. Setup Caching ---
# Use a writable temp dir so this works on Streamlit Cloud (app filesystem is read-only)
_cache_dir = os.path.join(tempfile.gettempdir(), "streamlit_range_gap_joblib_cache")
os.makedirs(_cache_dir, exist_ok=True)
memory = Memory(_cache_dir, verbose=0)

# --- 2. Load AI Models ---
print("Loading AI models...")
embedding_model = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')
print("AI models loaded successfully.")


# --- 3. Cached Analysis Functions ---
@memory.cache
def get_embeddings(keywords_tuple):
    """
    Encodes keywords into embeddings. Caches results to avoid re-computing.
    """
    print("Generating embeddings (cache miss)...")
    return embedding_model.encode(list(keywords_tuple), show_progress_bar=True)

def perform_topic_clustering(df, keyword_col):
    """
    Performs advanced topic clustering using embeddings of only the keyword text.
    Uses UMAP for dimensionality reduction and HDBSCAN for density-based clustering.
    This method automatically determines the number of clusters and identifies noise.
    """
    print("Performing advanced topic clustering (HDBSCAN)...")

    # Cluster only on unique keyword text for pure semantic grouping
    unique_keywords = df[keyword_col].dropna().unique()
    if len(unique_keywords) == 0:
        return None

    embeddings = get_embeddings(tuple(unique_keywords))
    
    # 1. Reduce dimensionality with UMAP
    # min_dist > 0 allows for more separation between clusters
    reducer = UMAP(n_neighbors=15, n_components=50, min_dist=0.1, metric='cosine', random_state=42)
    reduced_embeddings = reducer.fit_transform(embeddings)
    
    # 2. Cluster with HDBSCAN
    # min_cluster_size=5 is a good default to avoid tiny, meaningless clusters.
    # It will label noise points as -1.
    clusterer = hdbscan.HDBSCAN(min_cluster_size=5, gen_min_span_tree=True)
    cluster_labels = clusterer.fit_predict(reduced_embeddings)
    
    # Create a mapping from keyword to its new topic ID
    keyword_to_topic_map = pd.Series(cluster_labels, index=unique_keywords).to_dict()

    # Map the topic IDs back to the original dataframe
    return df[keyword_col].map(keyword_to_topic_map)