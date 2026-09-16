# Exam Paper Management System

A secure web application for managing encrypted question papers with multiple stakeholders (teacher, moderator, and exam cell).

## Features

- Secure encryption of question papers
- Role-based access control
- Paper review and approval workflow
- Random selection of question papers
- Secure decryption on exam day

## Setup

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

2. Initialize the database:
```bash
python
>>> from app import db, app
>>> with app.app_context():
...     db.create_all()
```

3. Create initial users (run in Python shell):
```python
from app import db, User
from werkzeug.security import generate_password_hash

# Create a teacher
teacher = User(
    username='teacher',
    password_hash=generate_password_hash('teacher123'),
    role='teacher'
)

# Create a moderator
moderator = User(
    username='moderator',
    password_hash=generate_password_hash('moderator123'),
    role='moderator'
)

# Create an exam cell user
exam_cell = User(
    username='examcell',
    password_hash=generate_password_hash('examcell123'),
    role='exam_cell'
)

db.session.add(teacher)
db.session.add(moderator)
db.session.add(exam_cell)
db.session.commit()
```

4. Run the application:
```bash
python app.py
```

## Usage

1. **Teacher's Role**:
   - Log in with teacher credentials
   - Upload question papers
   - View uploaded papers

2. **Moderator's Role**:
   - Log in with moderator credentials
   - Review and approve/reject papers
   - Select one paper randomly from approved papers
   - Provide decryption key to exam cell

3. **Exam Cell's Role**:
   - Log in with exam cell credentials
   - View selected papers
   - Decrypt and print papers on exam day

## Security Features

- All question papers are encrypted using Fernet encryption
- Role-based access control ensures proper workflow
- Papers can only be decrypted with the correct key
- Random selection of papers prevents bias

## Note

- Keep the decryption keys secure
- Change default passwords after first login
- Ensure proper backup of the database 