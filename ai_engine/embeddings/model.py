from sklearn.metrics.pairwise import cosine_similarity

from backend.app.services.embedding_service import get_embedding_model

class EmbeddingModel:
    def __init__(self):
        self._embedding_model = get_embedding_model()
    
    @classmethod
    def get_instance(cls):
        if not hasattr(cls, '_instance'):
            cls._instance = cls()
        return cls._instance
    
    @property
    def embedding_model(self):
        return self._embedding_model

    @staticmethod
    def vectorize_one(string):
        model = EmbeddingModel.get_instance()
        emb = model.embedding_model.encode(string, normalize_embeddings=True)
        return emb

    @staticmethod
    def vectorize(li_string):
        model = EmbeddingModel.get_instance()
        # Batch processing for GPU efficiency
        li_embeddings = model.embedding_model.encode(li_string, normalize_embeddings=True)
        return li_embeddings
    
    @staticmethod
    def cosine_sim(vec1, vec2):
        return cosine_similarity([vec1], [vec2])
