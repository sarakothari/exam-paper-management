from app import db, app, User
from werkzeug.security import generate_password_hash
import os

def init_db():
    with app.app_context():
        # Drop all existing tables
        db.drop_all()
        
        # Create all tables with new schema
        db.create_all()
        
        # Create initial users
        admin = User(
            username='admin',
            password_hash=generate_password_hash('admin123'),
            email='admin@example.com',
            full_name='Admin User',
            role='admin'
        )
        
        teacher = User(
            username='teacher',
            password_hash=generate_password_hash('teacher123'),
            email='teacher@example.com',
            full_name='Teacher User',
            role='teacher'
        )
        
        moderator = User(
            username='moderator',
            password_hash=generate_password_hash('moderator123'),
            email='moderator@example.com',
            full_name='Moderator User',
            role='moderator'
        )
        
        exam_cell = User(
            username='examcell',
            password_hash=generate_password_hash('examcell123'),
            email='examcell@example.com',
            full_name='Exam Cell User',
            role='exam_cell'
        )
        
        db.session.add(admin)
        db.session.add(teacher)
        db.session.add(moderator)
        db.session.add(exam_cell)
        db.session.commit()
        
        # Create uploads directory if it doesn't exist
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        print("Database initialized successfully!")

if __name__ == '__main__':
    init_db() 