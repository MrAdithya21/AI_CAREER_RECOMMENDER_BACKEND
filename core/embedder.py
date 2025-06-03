from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")

def embed_skills(skills):
    return model.encode(", ".join(skills), convert_to_tensor=True)
