from app import app, db, User
from werkzeug.security import generate_password_hash
import os
import shutil

def reset_database():
    with app.app_context():
        # Drop all tables
        db.drop_all()
        print("Dropped all tables.")
        
        # Create all tables
        db.create_all()
        print("Created all tables with new schema.")
        
        # Create admin user
        admin = User(
            username='admin',
            password_hash=generate_password_hash('admin123'),
            email='admin@example.com',
            full_name='Admin User',
            role='admin'
        )
        db.session.add(admin)
        db.session.commit()
        print("Created admin user.")
        
        # Clean up uploads directory
        uploads_dir = app.config['UPLOAD_FOLDER']
        if os.path.exists(uploads_dir):
            shutil.rmtree(uploads_dir)
        os.makedirs(uploads_dir)
        print("Reset uploads directory.")

if __name__ == '__main__':
    # Delete the database file if it exists
    db_path = 'instance/exam_papers.db'
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Deleted existing database: {db_path}")
    
    reset_database()
    print("Database reset complete!") 