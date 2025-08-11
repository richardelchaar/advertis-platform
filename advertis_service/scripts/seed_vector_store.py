# advertis_service/scripts/seed_vector_store.py
import sys
import os

# Add the parent directory to the path to allow app imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.vector_store import create_chroma_collection
from app.services.ad_inventory import ALL_ADS

def seed_database():
    """
    Connects to the vector store and seeds it with product data if it's empty.
    This is intended to be run as a one-off script.
    """
    print("--- Starting Vector Store Seeding ---")
    product_collection = create_chroma_collection()

    if product_collection.count() == 0:
        print("VECTOR_STORE: Database is empty. Seeding...")
        products_to_seed = ALL_ADS
        
        product_collection.add(
            ids=[p["id"] for p in products_to_seed],
            documents=[p["document"] for p in products_to_seed],
            metadatas=[p["metadata"] for p in products_to_seed]
        )
        print(f"SUCCESS: Seeding complete. Added {product_collection.count()} products.")
    else:
        print(f"INFO: Database already contains {product_collection.count()} products. Skipping seed.")

if __name__ == "__main__":
    seed_database() 