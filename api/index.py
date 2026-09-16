import sys
import os

# Add parent directory to path so we can import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db

# Universal WSGI middleware to normalize request paths on Vercel
class VercelPathFix(object):
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        # 1. Prefer original browser URI from Vercel headers if available
        raw = (
            environ.get('HTTP_X_FORWARDED_URI')
            or environ.get('REQUEST_URI')
            or environ.get('RAW_URI')
        )
        if raw:
            path = raw.split('?')[0]
        else:
            path = environ.get('PATH_INFO', '')

        # 2. Strip any serverless file prefix (/api/index.py or /api/index)
        for prefix in ('/api/index.py', '/api/index'):
            if path.startswith(prefix):
                path = path[len(prefix):]
                break

        # 3. Ensure a valid non-empty route path
        environ['PATH_INFO'] = path if (path and path.startswith('/')) else ('/' + path if path else '/')
        return self.wsgi_app(environ, start_response)

app.wsgi_app = VercelPathFix(app.wsgi_app)

# Initialize DB tables safely on cold start
try:
    with app.app_context():
        db.create_all()
except Exception as e:
    print(f"Database initialization notice: {e}")
