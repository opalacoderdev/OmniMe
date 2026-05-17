import os
import numpy as np
from typing import Optional

# Singleton pattern for the embedding model to avoid reloading it
_model = None

def _get_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError("Please install sentence-transformers: pip install sentence-transformers")
        
        # We use a lightweight multilingual model
        # It downloads ~470MB on first use and caches it locally
        model_name = "paraphrase-multilingual-MiniLM-L12-v2"
        _model = SentenceTransformer(model_name)
    return _model

def get_embedding(text: str) -> np.ndarray:
    """Returns the embedding vector for the given text."""
    if not text.strip():
        # Return a zero vector of size 384 (standard for MiniLM)
        return np.zeros(384, dtype=np.float32)
    model = _get_model()
    # encode() returns a numpy array
    return model.encode(text)

def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """Computes the cosine similarity between two vectors."""
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(np.dot(vec1, vec2) / (norm1 * norm2))

# Intent Anchors (Multilingual)
INTENT_ANCHORS = {
    "chat": [
        "hello", "hi", "how are you", "what are the commands", "list", "help", "clear",
        "olá", "oi", "quais os comandos", "listar", "ajuda", "limpar", "tudo bem",
        "hola", "ayuda", "comandos"
    ],
    "plan": [
        "create an app", "write code", "build a website", "refactor the function", "make a script",
        "crie um aplicativo", "escreva o código", "faça um script", "construa um site", "refatorar",
        "crea una aplicación", "escribe el código", "construye"
    ],
    "question": [
        "how does python work", "what is a closure", "explain react hooks", "why is this happening",
        "como o python funciona", "o que é isso", "explique", "por que isso acontece",
        "cómo funciona", "qué es", "explica"
    ]
}

_intent_embeddings = {}

def classify_intent_embedded(text: str) -> str:
    """Classifies intent using cosine similarity against multilingual anchors."""
    global _intent_embeddings
    if not _intent_embeddings:
        # Lazy initialization
        for intent, phrases in INTENT_ANCHORS.items():
            _intent_embeddings[intent] = [get_embedding(p) for p in phrases]
            
    text_vec = get_embedding(text)
    
    best_intent = "chat"
    highest_sim = -1.0
    
    for intent, vec_list in _intent_embeddings.items():
        for anchor_vec in vec_list:
            sim = cosine_similarity(text_vec, anchor_vec)
            if sim > highest_sim:
                highest_sim = sim
                best_intent = intent
                
    # If the highest similarity is very low, default to chat
    if highest_sim < 0.2:
        return "chat"
        
    return best_intent

