#!/bin/sh

# This tells the script to exit immediately if any command fails
set -e

# Run the database seeder script.
# Inside the Docker container, the app's config will correctly use
# the default CHROMA_URL of http://chroma_db:8000.
echo "--- Running vector store seeder on startup ---"
python -m scripts.seed_vector_store

# After the seeder finishes, execute the main command passed to this script
# (which will be the uvicorn server CMD from our Dockerfile).
exec "$@" 