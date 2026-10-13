import numpy as np

def cosine_similarity(a, b):
    a = np.array(a)
    b = np.array(b)

    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)

def top_k(query_vec, matrix, k=5):
    q = np.asarray(query_vec, dtype=float)
    m = np.asarray(matrix, dtype=float)          # list of lists from the database -> array (n, dim)
    if m.size == 0:
        return np.array([], dtype=int), np.array([])

    denom = np.linalg.norm(m, axis=1) * np.linalg.norm(q)
    scores = np.divide(m @ q, denom, out=np.zeros(len(m)), where=denom != 0)   # zero vector -> score 0
    idx = np.argsort(-scores)[:k]
    return idx, scores[idx]