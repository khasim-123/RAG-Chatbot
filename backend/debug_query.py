from app.config import get_settings
from app.embeddings import embed_query
from app.vectorstore import VectorStore

settings = get_settings()
store = VectorStore(persist_dir=settings.chroma_db_dir, collection_name=settings.collection_name)

query = "What courses does Vignan IIT offer?"
vec = embed_query(query, settings.embedding_model)
results = store.query(vec, top_k=20)

for i, r in enumerate(results, 1):
    marker = " <-- COURSES PAGE" if "courses-offered" in r.url else ""
    print(f"{i}. dist={r.distance:.3f}  {r.url}{marker}")

print("\n\n--- Raw content of /courses-offered chunks ---")
all_docs = store.collection.get(where={"url": "https://vignaniit.edu.in/courses-offered"})
for doc in all_docs["documents"]:
    print(doc[:800])
    print("---")