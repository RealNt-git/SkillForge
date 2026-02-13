import traceback
from database import db_lock, c, conn, log_error, get_all_knowledge_base, add_knowledge_item, search_knowledge_base_simple, init_knowledge_base

# Ensure knowledge base is initialized
init_knowledge_base()

# Vector DB setup
chromadb_available = False
try:
    import chromadb
    from chromadb.utils import embedding_functions
    chromadb_available = True
except ImportError:
    chromadb_available = False

vector_collection = None
if chromadb_available:
    try:
        client = chromadb.PersistentClient(path="./chroma_db")
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="intfloat/multilingual-e5-small"
        )
        try:
            vector_collection = client.get_collection("analyst_skills", embedding_function=ef)
        except:
            vector_collection = client.create_collection("analyst_skills", embedding_function=ef)
            # Load from knowledge_base
            with db_lock:
                c.execute("SELECT title, link, tags FROM knowledge_base")
                rows = c.fetchall()
            documents = []
            metadatas = []
            ids = []
            for i, (title, link, tags) in enumerate(rows):
                documents.append(f"{title} {tags}")
                metadatas.append({"link": link, "title": title})
                ids.append(f"doc_{i}")
            if documents:
                vector_collection.add(documents=documents, metadatas=metadatas, ids=ids)
    except Exception as e:
        log_error("VectorDBInit", str(e), traceback.format_exc())
        vector_collection = None

def search_resources(query: str) -> str:
    if vector_collection is not None:
        try:
            results = vector_collection.query(query_texts=[query], n_results=5)
            output = []
            for i in range(len(results['documents'][0])):
                title = results['metadatas'][0][i]['title']
                link = results['metadatas'][0][i]['link']
                output.append(f"- [{title}]({link})")
            return "\n".join(output) if output else "Ничего не найдено."
        except Exception as e:
            log_error("VectorSearch", str(e), traceback.format_exc())
            # fallback to simple search
    # Simple search fallback
    rows = search_knowledge_base_simple(query)
    if rows:
        return "\n".join([f"- [{title}]({link})" for title, link in rows])
    else:
        return "Ничего не найдено. Попробуйте изменить запрос."