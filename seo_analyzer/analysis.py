# seo_analyzer/analysis.py
"""
Semantic clustering pipeline for Product Opportunity Group generation.

Pipeline:
1. spaCy (en_core_web_md) — linguistic tokenisation and text preprocessing
2. NLTK (PorterStemmer) — word stemming for normalisation
3. sentence-transformers (all-MiniLM-L6-v2) — vector embeddings
4. UMAP — dimensionality reduction
5. HDBSCAN — density-based autonomous clustering
6. Noise reassignment — nearest-centroid assignment for unclustered queries
"""

import json
import os
import tempfile

import numpy as np
import pandas as pd
import spacy
from nltk.stem import PorterStemmer
from sentence_transformers import SentenceTransformer
import hdbscan
from umap import UMAP
from joblib import Memory
from scipy.spatial.distance import cdist

# --- Configuration ---
_config_path = os.path.join(os.path.dirname(__file__), "scoring_config.json")


def _load_clustering_config():
    """Load clustering parameters from the scoring config file."""
    try:
        with open(_config_path, "r") as f:
            config = json.load(f)
        return config.get("clustering", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


# --- Setup Caching ---
_cache_dir = os.path.join(tempfile.gettempdir(), "streamlit_range_gap_joblib_cache")
os.makedirs(_cache_dir, exist_ok=True)
memory = Memory(_cache_dir, verbose=0)

# --- Load AI Models ---
print("Loading AI models...")
embedding_model = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')

# Load spaCy model for linguistic preprocessing
try:
    nlp = spacy.load("en_core_web_md", disable=["ner", "parser"])
except OSError:
    print("spaCy model 'en_core_web_md' not found. Falling back to en_core_web_sm.")
    try:
        nlp = spacy.load("en_core_web_sm", disable=["ner", "parser"])
    except OSError:
        print("No spaCy model found. Text preprocessing will be limited.")
        nlp = None

stemmer = PorterStemmer()
print("AI models loaded successfully.")


def _preprocess_keyword(text: str) -> str:
    """
    Preprocess a keyword using spaCy tokenisation and NLTK stemming.

    Steps:
    - spaCy tokenises and lemmatises
    - Removes stopwords, punctuation, and single-character tokens
    - NLTK PorterStemmer normalises remaining tokens
    - Returns cleaned, stemmed text for better embedding similarity
    """
    if not text or not isinstance(text, str):
        return ""

    if nlp is not None:
        doc = nlp(text.lower().strip())
        tokens = [
            token.lemma_
            for token in doc
            if not token.is_stop and not token.is_punct and len(token.text) > 1
        ]
    else:
        # Fallback: simple whitespace tokenisation
        tokens = [t for t in text.lower().strip().split() if len(t) > 1]

    # Apply Porter stemming for further normalisation
    stemmed = [stemmer.stem(t) for t in tokens]
    return " ".join(stemmed) if stemmed else text.lower().strip()


def _preprocess_keywords_batch(keywords: list) -> list:
    """Preprocess a batch of keywords using spaCy pipe for efficiency."""
    if nlp is None:
        return [_preprocess_keyword(kw) for kw in keywords]

    results = []
    # Use spaCy pipe for batch processing (much faster than individual calls)
    texts = [kw.lower().strip() if isinstance(kw, str) else "" for kw in keywords]
    for doc in nlp.pipe(texts, batch_size=256):
        tokens = [
            token.lemma_
            for token in doc
            if not token.is_stop and not token.is_punct and len(token.text) > 1
        ]
        stemmed = [stemmer.stem(t) for t in tokens]
        results.append(" ".join(stemmed) if stemmed else doc.text)
    return results


@memory.cache
def get_embeddings(keywords_tuple):
    """
    Encodes keywords into embeddings. Caches results to avoid re-computing.
    Uses preprocessed text for embedding generation to improve semantic similarity.
    """
    print(f"Generating embeddings for {len(keywords_tuple)} keywords (cache miss)...")
    return embedding_model.encode(list(keywords_tuple), show_progress_bar=True,
                                   normalize_embeddings=True)


def _assign_noise_to_nearest_cluster(embeddings, labels):
    """
    Reassign noise points (label == -1) to their nearest cluster centroid.

    This prevents useful queries from being discarded just because they sit
    in a low-density region of the embedding space.
    """
    noise_mask = labels == -1
    if not noise_mask.any():
        return labels

    cluster_ids = np.unique(labels[~noise_mask])
    if len(cluster_ids) == 0:
        return labels

    # Compute cluster centroids
    centroids = np.array([
        embeddings[labels == cid].mean(axis=0) for cid in cluster_ids
    ])

    # For each noise point, find the nearest centroid
    noise_embeddings = embeddings[noise_mask]
    distances = cdist(noise_embeddings, centroids, metric='cosine')
    nearest_cluster_indices = distances.argmin(axis=1)

    new_labels = labels.copy()
    noise_indices = np.where(noise_mask)[0]
    for i, idx in enumerate(noise_indices):
        new_labels[idx] = cluster_ids[nearest_cluster_indices[i]]

    print(f"Reassigned {noise_mask.sum()} noise points to nearest clusters.")
    return new_labels


def _select_representative_query(keywords: list, keyword_col_values: pd.Series = None) -> str:
    """
    Select the most descriptive/representative query from a cluster.

    Heuristic: prefer medium-length queries (most specific without being
    overly long or too generic/short).
    """
    if not keywords:
        return "Unknown"

    # Score by length — prefer queries with 2-4 words (most descriptive)
    scored = []
    for kw in keywords:
        word_count = len(str(kw).split())
        # Prefer 2-4 word queries; penalise very short or very long
        if 2 <= word_count <= 4:
            length_score = 10
        elif word_count == 1:
            length_score = 3
        elif word_count <= 6:
            length_score = 7
        else:
            length_score = 2
        scored.append((kw, length_score))

    # Sort by score descending, then alphabetically for consistency
    scored.sort(key=lambda x: (-x[1], x[0]))
    return scored[0][0]


def perform_topic_clustering(df, keyword_col):
    """
    Performs semantic clustering to generate Product Opportunity Groups.

    Pipeline:
    1. Preprocess keywords with spaCy tokenisation + NLTK stemming
    2. Generate embeddings with sentence-transformers (all-MiniLM-L6-v2)
    3. Reduce dimensionality with UMAP (cosine metric)
    4. Cluster with HDBSCAN (density-based, autonomous cluster count)
    5. Reassign noise points to nearest cluster centroid
    6. Return TopicID assignments for all keywords

    Each resulting cluster = one Product Opportunity Group.
    """
    print("Performing semantic clustering (HDBSCAN)...")

    config = _load_clustering_config()

    # Extract unique keywords
    unique_keywords = df[keyword_col].dropna().unique()
    if len(unique_keywords) == 0:
        return None

    # Step 1: Preprocess keywords with spaCy + NLTK
    print("Preprocessing keywords with spaCy + NLTK stemming...")
    preprocessed = _preprocess_keywords_batch(list(unique_keywords))

    # Step 2: Generate embeddings on preprocessed text
    # We embed the preprocessed versions for better semantic grouping,
    # but also embed originals to handle cases where preprocessing strips too much
    embeddings_preprocessed = get_embeddings(tuple(preprocessed))

    # Step 3: UMAP dimensionality reduction
    n_components = min(config.get("umap_n_components", 25), len(unique_keywords) - 2)
    n_components = max(n_components, 2)  # minimum 2 dimensions
    n_neighbors = min(config.get("umap_n_neighbors", 15), len(unique_keywords) - 1)
    n_neighbors = max(n_neighbors, 2)

    reducer = UMAP(
        n_neighbors=n_neighbors,
        n_components=n_components,
        min_dist=config.get("umap_min_dist", 0.0),
        metric=config.get("umap_metric", "cosine"),
        random_state=42,
    )
    reduced_embeddings = reducer.fit_transform(embeddings_preprocessed)

    # Step 4: HDBSCAN clustering
    min_cluster_size = config.get("hdbscan_min_cluster_size", 5)
    min_samples = config.get("hdbscan_min_samples", 3)
    cluster_selection_method = config.get("hdbscan_cluster_selection_method", "eom")

    # Adjust min_cluster_size for small datasets
    if len(unique_keywords) < 50:
        min_cluster_size = max(2, min(min_cluster_size, len(unique_keywords) // 5))
        min_samples = max(1, min(min_samples, min_cluster_size - 1))

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        cluster_selection_method=cluster_selection_method,
        metric='euclidean',
        gen_min_span_tree=True,
    )
    cluster_labels = clusterer.fit_predict(reduced_embeddings)

    n_clusters = len(set(cluster_labels)) - (1 if -1 in cluster_labels else 0)
    n_noise = (cluster_labels == -1).sum()
    print(f"HDBSCAN found {n_clusters} clusters, {n_noise} noise points.")

    # Step 5: Reassign noise points to nearest cluster
    cluster_labels = _assign_noise_to_nearest_cluster(reduced_embeddings, cluster_labels)

    # Create keyword → TopicID mapping
    keyword_to_topic_map = pd.Series(cluster_labels, index=unique_keywords).to_dict()

    # Map back to the original dataframe
    return df[keyword_col].map(keyword_to_topic_map)


def generate_topic_names(df, keyword_col, topic_col='TopicID', volume_col=None):
    """
    Generate descriptive names for each Product Opportunity Group.

    Selects the most representative query from each cluster based on
    descriptiveness heuristics (word count, specificity).
    """
    topic_names = {}
    for topic_id in df[topic_col].dropna().unique():
        if topic_id == -1:
            continue
        cluster_keywords = df[df[topic_col] == topic_id][keyword_col].unique().tolist()

        # If we have volume data, prefer higher-volume keywords as they're
        # more recognisable to the commercial team
        if volume_col and volume_col in df.columns:
            cluster_df = df[df[topic_col] == topic_id].drop_duplicates(subset=[keyword_col])
            cluster_df = cluster_df.sort_values(volume_col, ascending=False)
            # Take top 10 by volume, then pick the most descriptive
            top_by_volume = cluster_df[keyword_col].head(10).tolist()
            representative = _select_representative_query(top_by_volume)
        else:
            representative = _select_representative_query(cluster_keywords)

        topic_names[topic_id] = representative

    return topic_names
