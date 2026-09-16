from app import app, db

def create_database():
    with app.app_context():
        # Create all tables
        db.create_all()
        print("Database created successfully!")

if __name__ == "__main__":
    create_database() 