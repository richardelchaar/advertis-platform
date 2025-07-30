import chromadb
from chromadb.utils import embedding_functions
from app import config
from app.services.ad_inventory import ALL_ADS 

# --- Client Initialization (No Change) ---
# This points our application to the ChromaDB container running in Docker.
chroma_client = chromadb.HttpClient(host="chroma_db", port=8000)

openai_ef = embedding_functions.OpenAIEmbeddingFunction(
                api_key=config.OPENAI_API_KEY,
                model_name="text-embedding-3-small"
            )


# --- Collection Setup (No Change) ---
# A "collection" in Chroma is like a database table. This is where our ad vectors will live.
product_collection = chroma_client.get_or_create_collection(
    name="advertis_products",
    embedding_function=openai_ef
)


# --- Database Seeding Function (REVISED) ---
def seed_database():
    """
    Checks if the database is empty and seeds it with products
    using our new "Universal + Vertical-Specific" metadata structure.
    """
    if product_collection.count() == 0:
        print("VECTOR_STORE: Database is empty. Seeding with new scalable data model...")
        products_to_seed = ALL_ADS

        
        product_collection.add(
            ids=[p["id"] for p in products_to_seed],
            documents=[p["document"] for p in products_to_seed],
            metadatas=[p["metadata"] for p in products_to_seed]
        )
        print(f"VECTOR_STORE: Seeding complete. Added {product_collection.count()} products.")
    else:
        print(f"VECTOR_STORE: Database already contains {product_collection.count()} products. Skipping seed.")

# --- Initialization (No Change) ---
print("VECTOR_STORE: ChromaDB client initialized.")
seed_database()