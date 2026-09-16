from app import db, app, User, QuestionPaper, PaperHistory, DecryptionRequest
import os
import shutil

def clean_database():
    with app.app_context():
        # Drop all tables
        db.drop_all()
        
        # Recreate all tables with new schema
        db.create_all()
        
        # Clean up uploads directory
        uploads_dir = app.config['UPLOAD_FOLDER']
        if os.path.exists(uploads_dir):
            # Remove all files in uploads directory
            shutil.rmtree(uploads_dir)
            # Recreate the empty uploads directory
            os.makedirs(uploads_dir)
            
        print("Database and uploads directory cleaned successfully!")

if __name__ == '__main__':
    clean_database() 