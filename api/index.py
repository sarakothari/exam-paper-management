import sys
import os

# Add parent directory to path so we can import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db

# Initialize DB tables on cold start (Vercel Postgres)
with app.app_context():
    db.create_all()

# Vercel expects the WSGI app to be named 'app' in the handler module
# The @vercel/python runtime automatically detects and serves it
