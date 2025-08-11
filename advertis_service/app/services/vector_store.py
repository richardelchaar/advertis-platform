# advertis_service/app/services/vector_store.py
import chromadb
from chromadb.utils import embedding_functions
from app import config
from chromadb.api.models.Collection import Collection

def create_chroma_collection() -> Collection:
    """
    Creates and returns a ChromaDB collection object.
    This function is the single source of truth for our vector store connection.
    """
    print("VECTOR_STORE: Creating ChromaDB client and collection...")
    
    chroma_client = chromadb.HttpClient(
        host=config.CHROMA_HOST, 
        port=config.CHROMA_PORT
    )

    openai_ef = embedding_functions.OpenAIEmbeddingFunction(
                api_key=config.OPENAI_API_KEY,
                model_name="text-embedding-3-small"
            )

    product_collection = chroma_client.get_or_create_collection(
        name="advertis_products",
        embedding_function=openai_ef
    )
    
    return product_collection