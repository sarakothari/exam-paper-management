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
        orig = environ.get('HTTP_X_FORWARDED_URI') or environ.get('HTTP_X_MATCHED_PATH')
        if orig and not orig.startswith('/api/index'):
            environ['PATH_INFO'] = orig.split('?')[0]
        elif path.startswith('/api/index'):
            remainder = path[len('/api/index'):]
            environ['PATH_INFO'] = remainder if (remainder and remainder != '') else '/'
        return self.wsgi_app(environ, start_response)

app.wsgi_app = VercelPathFix(app.wsgi_app)

# Initialize DB tables safely on cold start
try:
    with app.app_context():
        db.create_all()
except Exception as e:
    print(f"Database initialization notice: {e}")
