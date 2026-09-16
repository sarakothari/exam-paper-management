import sys
import os

# Add parent directory to path so we can import app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db

# WSGI middleware to fix Vercel's internal rewrite PATH_INFO
class VercelPathFix(object):
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')

        # 1. If path starts with /api/index, strip the prefix to get real route
        if path.startswith('/api/index'):
            sub = path[len('/api/index'):]
            path = sub if (sub and sub.startswith('/')) else ('/' + sub if sub else '/')

        # 2. Check if Vercel passed original route in headers/raw uri
        if path in ('', '/'):
            raw = environ.get('REQUEST_URI') or environ.get('RAW_URI') or environ.get('HTTP_X_FORWARDED_URI')
            if raw and not raw.startswith('/api'):
                path = raw.split('?')[0]

        environ['PATH_INFO'] = path if path else '/'
        return self.wsgi_app(environ, start_response)

app.wsgi_app = VercelPathFix(app.wsgi_app)

# Initialize DB tables safely on cold start
try:
    with app.app_context():
        db.create_all()
except Exception as e:
    print(f"Database initialization notice: {e}")
