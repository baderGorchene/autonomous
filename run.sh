#!/bin/bash

# Apply database migrations (placeholder - actual alembic command would go here)
# For now, assuming `src/main.py` handles `Base.metadata.create_all()` on startup,
# or that the database is pre-migrated. For production, `alembic upgrade head` is recommended.
echo "Skipping database migrations for MVP setup. Ensure DB is initialized."

# Start Gunicorn
# Assuming the FastAPI app instance is named 'app' in 'src/main.py'
exec gunicorn src.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
