from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet
import os
import io
import random
from datetime import datetime
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-fallback-key-change-in-production')

# Detect Vercel environment
IS_VERCEL = bool(os.environ.get('VERCEL'))

# Database configuration — use PostgreSQL on Vercel, SQLite locally
database_url = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL') or os.environ.get('STORAGE_URL')
if database_url:
    # Handle legacy postgres:// connection strings (Heroku/Vercel Postgres)
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
elif IS_VERCEL:
    # On Vercel, the root filesystem is read-only; use /tmp for SQLite if external DB is not set yet
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/exam_papers.db'
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///exam_papers.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Local uploads folder (only used in local dev)
if not IS_VERCEL:
    app.config['UPLOAD_FOLDER'] = 'uploads'
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


# ---------------------------------------------------------------------------
# Storage Abstraction — Vercel Blob vs Local Filesystem
# ---------------------------------------------------------------------------

def storage_upload(filename, data: bytes) -> str:
    """Upload binary data. Returns a URL (Vercel) or file path (local)."""
    if IS_VERCEL:
        import vercel_blob
        result = vercel_blob.put(filename, data, {"addRandomSuffix": "true"})
        return result['url']
    else:
        path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        with open(path, 'wb') as f:
            f.write(data)
        return path


def storage_download(identifier: str) -> bytes:
    """Download binary data. identifier is a URL (Vercel) or file path (local)."""
    if IS_VERCEL:
        import requests as req
        token = os.environ.get('BLOB_READ_WRITE_TOKEN', '')
        headers = {'Authorization': f'Bearer {token}'} if token else {}
        resp = req.get(identifier, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.content
    else:
        with open(identifier, 'rb') as f:
            return f.read()


def storage_delete(identifier: str):
    """Delete a stored file/blob. Silently ignores errors."""
    if IS_VERCEL:
        try:
            import vercel_blob
            vercel_blob.delete([identifier])
        except Exception:
            pass
    else:
        try:
            os.remove(identifier)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Database Models
# ---------------------------------------------------------------------------

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin, teacher, moderator, exam_cell
    email = db.Column(db.String(120), unique=True, nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    subject = db.Column(db.String(20))  # maths, dbms, os

    def __init__(self, username, password_hash, email, full_name, role, subject=None):
        self.username = username
        self.password_hash = password_hash
        self.email = email
        self.full_name = full_name
        self.role = role
        self.subject = subject


class QuestionPaper(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    # file_path stores a URL on Vercel Blob, or a local file path in dev
    file_path = db.Column(db.String(1024), nullable=False)
    encrypted_file_path = db.Column(db.String(1024), nullable=False)
    # encryption_key stores the Fernet key (base64 string) in the DB — replaces key files on disk
    encryption_key = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False)  # uploaded, approved, selected
    subject = db.Column(db.String(20), nullable=False)  # maths, dbms, os
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    moderator_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    exam_date = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    history = db.relationship('PaperHistory', backref='paper', lazy=True)
    teacher = db.relationship('User', foreign_keys=[teacher_id], backref='uploaded_papers')
    moderator = db.relationship('User', foreign_keys=[moderator_id], backref='moderated_papers')


class PaperHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.Integer, db.ForeignKey('question_paper.id'), nullable=False)
    moderator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(20), nullable=False)  # approve, reject
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    moderator = db.relationship('User', backref='review_history')


class DecryptionRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.Integer, db.ForeignKey('question_paper.id'), nullable=False)
    requester_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False)  # pending, approved, rejected
    request_date = db.Column(db.DateTime, default=datetime.utcnow)
    approval_date = db.Column(db.DateTime)
    approver_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    reason = db.Column(db.Text)

    paper = db.relationship('QuestionPaper', backref='decryption_requests')
    requester = db.relationship('User', foreign_keys=[requester_id], backref='decryption_requests')
    approver = db.relationship('User', foreign_keys=[approver_id], backref='approved_requests')


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ---------------------------------------------------------------------------
# Encryption Utilities
# ---------------------------------------------------------------------------

def generate_key() -> bytes:
    return Fernet.generate_key()


def encrypt_data(data: bytes, key: bytes) -> bytes:
    """Encrypt binary data in memory and return encrypted bytes."""
    return Fernet(key).encrypt(data)


def decrypt_data(encrypted_data: bytes, key: bytes) -> bytes:
    """Decrypt binary data in memory and return decrypted bytes."""
    return Fernet(key).decrypt(encrypted_data)


def is_file_encrypted(file_path_or_url: str) -> bool:
    """Check if a stored file/blob is Fernet-encrypted by reading its header."""
    try:
        if IS_VERCEL:
            # Download just the first chunk to check the header
            import requests as req
            token = os.environ.get('BLOB_READ_WRITE_TOKEN', '')
            headers = {'Authorization': f'Bearer {token}'} if token else {}
            resp = req.get(file_path_or_url, headers=headers, stream=True, timeout=10)
            header = b''
            for chunk in resp.iter_content(chunk_size=16):
                header = chunk[:16]
                break
        else:
            with open(file_path_or_url, 'rb') as f:
                header = f.read(16)
        return header.startswith(b'gAAAAAB')
    except Exception:
        return False


def _get_key_for_paper(paper) -> bytes:
    """
    Retrieve the Fernet key for a paper.
    New papers: key is stored in paper.encryption_key (DB column).
    Legacy papers (pre-Blob): key is stored in a local key file.
    """
    if paper.encryption_key:
        return paper.encryption_key.encode('utf-8')
    # Legacy fallback: read key file from local disk
    if not IS_VERCEL:
        key_filename = f"key_{os.path.basename(paper.file_path).replace('encrypted_', '')}.txt"
        key_path = os.path.join(app.config['UPLOAD_FOLDER'], key_filename)
        with open(key_path, 'rb') as kf:
            return kf.read()
    raise ValueError("No encryption key found for this paper")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
@app.route('/api/index')
def index():
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email')
        full_name = request.form.get('full_name')
        role = request.form.get('role')
        subject = request.form.get('subject')

        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('Email already exists')
            return redirect(url_for('register'))

        if role == 'exam_cell' and User.query.filter_by(role='exam_cell').first():
            flash('An exam cell user already exists. Please choose a different role.')
            return redirect(url_for('register'))

        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            email=email,
            full_name=full_name,
            role=role,
            subject=subject if role in ['teacher', 'moderator'] else None
        )
        db.session.add(user)
        db.session.commit()

        flash('Registration successful! Please login.')
        return redirect(url_for('login'))

    exam_cell_exists = User.query.filter_by(role='exam_cell').first() is not None
    return render_template('register.html', exam_cell_exists=exam_cell_exists)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'teacher':
        papers = QuestionPaper.query.filter_by(teacher_id=current_user.id).all()
    elif current_user.role == 'moderator':
        papers = QuestionPaper.query.filter_by(
            status='uploaded',
            subject=current_user.subject
        ).all()
    elif current_user.role == 'exam_cell':
        papers = QuestionPaper.query.all()
        decryption_requests = DecryptionRequest.query.filter_by(status='pending').all()
        selected_papers = {
            'maths': QuestionPaper.query.filter_by(status='selected', subject='maths').first(),
            'dbms': QuestionPaper.query.filter_by(status='selected', subject='dbms').first(),
            'os': QuestionPaper.query.filter_by(status='selected', subject='os').first()
        }
        return render_template('dashboard.html',
                               papers=papers,
                               decryption_requests=decryption_requests,
                               selected_papers=selected_papers)
    else:  # admin
        papers = QuestionPaper.query.all()

    # Annotate encryption status (local only — skip on Vercel for performance)
    for paper in papers:
        if IS_VERCEL:
            paper.is_encrypted = bool(paper.encryption_key)
        else:
            paper.is_encrypted = is_file_encrypted(paper.file_path)

    return render_template('dashboard.html', papers=papers)


@app.route('/upload_paper', methods=['GET', 'POST'])
@login_required
def upload_paper():
    if current_user.role != 'teacher':
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected')
            return redirect(request.url)

        file = request.files['file']
        if file.filename == '':
            flash('No file selected')
            return redirect(request.url)

        if not file.filename.lower().endswith(('.doc', '.docx', '.pdf')):
            flash('Invalid file type. Please upload a Word or PDF file.')
            return redirect(request.url)

        try:
            # Read file content into memory
            file_data = file.read()

            # Generate encryption key
            key = generate_key()

            # Encrypt in memory
            encrypted_data = encrypt_data(file_data, key)

            # Build a storage-friendly filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            original_filename = secure_filename(file.filename)
            encrypted_filename = f"encrypted_{timestamp}_{original_filename}"

            # Upload encrypted data to Vercel Blob or local disk
            file_identifier = storage_upload(encrypted_filename, encrypted_data)

            # Store key in DB (as UTF-8 string — Fernet keys are already base64)
            paper = QuestionPaper(
                title=request.form.get('title'),
                file_path=file_identifier,
                encrypted_file_path=file_identifier,
                encryption_key=key.decode('utf-8'),
                status='uploaded',
                teacher_id=current_user.id,
                subject=current_user.subject
            )
            db.session.add(paper)
            db.session.commit()

            flash('Question paper uploaded and encrypted successfully')
            return redirect(url_for('dashboard'))

        except Exception as e:
            flash(f'Error uploading file: {str(e)}')
            return redirect(request.url)

    return render_template('upload_paper.html')


@app.route('/request_decryption/<int:paper_id>', methods=['GET', 'POST'])
@login_required
def request_decryption(paper_id):
    paper = db.session.get(QuestionPaper, paper_id)
    if paper is None:
        flash('Paper not found')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        reason = request.form.get('reason', '')

        existing_request = DecryptionRequest.query.filter_by(
            paper_id=paper_id,
            requester_id=current_user.id,
            status='pending'
        ).first()

        if existing_request:
            flash('You already have a pending request for this paper')
            return redirect(url_for('dashboard'))

        decryption_request = DecryptionRequest(
            paper_id=paper_id,
            requester_id=current_user.id,
            status='pending',
            reason=reason
        )
        db.session.add(decryption_request)
        db.session.commit()

        flash('Decryption request submitted successfully')
        return redirect(url_for('dashboard'))

    return render_template('request_decryption.html', paper=paper)


@app.route('/manage_decryption_requests')
@login_required
def manage_decryption_requests():
    if current_user.role not in ['admin', 'exam_cell']:
        flash('Unauthorized access')
        return redirect(url_for('dashboard'))

    pending_requests = DecryptionRequest.query.filter_by(status='pending').all()
    return render_template('manage_decryption_requests.html', requests=pending_requests)


@app.route('/approve_decryption/<int:request_id>', methods=['POST'])
@login_required
def approve_decryption(request_id):
    if current_user.role not in ['admin', 'exam_cell']:
        flash('Unauthorized access')
        return redirect(url_for('dashboard'))

    decryption_request = db.session.get(DecryptionRequest, request_id)
    if decryption_request is None:
        flash('Request not found')
        return redirect(url_for('manage_decryption_requests'))

    decryption_request.status = 'approved'
    decryption_request.approval_date = datetime.utcnow()
    decryption_request.approver_id = current_user.id
    db.session.commit()

    flash('Decryption request approved')
    return redirect(url_for('manage_decryption_requests'))


@app.route('/reject_decryption/<int:request_id>', methods=['POST'])
@login_required
def reject_decryption(request_id):
    if current_user.role != 'exam_cell':
        flash('Unauthorized access')
        return redirect(url_for('dashboard'))

    decryption_request = db.session.get(DecryptionRequest, request_id)
    if decryption_request is None:
        flash('Request not found')
        return redirect(url_for('dashboard'))

    decryption_request.status = 'rejected'
    decryption_request.approval_date = datetime.utcnow()
    decryption_request.approver_id = current_user.id
    db.session.commit()

    flash('Decryption request rejected')
    return redirect(url_for('dashboard'))


@app.route('/download_paper/<int:paper_id>')
@login_required
def download_paper(paper_id):
    paper = db.session.get(QuestionPaper, paper_id)
    if paper is None:
        flash('Paper not found')
        return redirect(url_for('dashboard'))

    # Permission check
    if current_user.role != 'admin':
        approved_request = DecryptionRequest.query.filter_by(
            paper_id=paper_id,
            requester_id=current_user.id,
            status='approved'
        ).first()

        if not approved_request:
            flash('You need admin approval to download this file')
            return redirect(url_for('request_decryption', paper_id=paper_id))

    try:
        # Retrieve encryption key
        key = _get_key_for_paper(paper)

        # Download encrypted data from Blob or local disk
        encrypted_data = storage_download(paper.file_path)

        # Decrypt in memory — no temp files needed
        decrypted_data = decrypt_data(encrypted_data, key)

        # Derive a clean download filename
        basename = os.path.basename(paper.file_path.split('?')[0])  # strip query params for blob URLs
        download_name = basename.replace('encrypted_', 'decrypted_')
        # Strip timestamp prefix if present (e.g. decrypted_20250425_165558_paper.pdf → paper.pdf)
        parts = download_name.split('_')
        if len(parts) > 3 and parts[1].isdigit() and parts[2].isdigit():
            download_name = '_'.join(parts[3:])

        return send_file(
            io.BytesIO(decrypted_data),
            as_attachment=True,
            download_name=download_name or 'decrypted_paper.pdf'
        )

    except Exception as e:
        flash(f'Error decrypting file: {str(e)}')
        return redirect(url_for('dashboard'))


@app.route('/review_paper/<int:paper_id>', methods=['GET', 'POST'])
@login_required
def review_paper(paper_id):
    if current_user.role != 'moderator':
        return redirect(url_for('dashboard'))

    paper = db.session.get(QuestionPaper, paper_id)
    if paper is None:
        flash('Paper not found')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        action = request.form.get('action')
        comment = request.form.get('comment', '')

        if action == 'approve':
            paper.status = 'approved'
            paper.moderator_id = current_user.id
            history = PaperHistory(
                paper_id=paper.id,
                moderator_id=current_user.id,
                action='approve',
                comment=comment
            )
            db.session.add(history)
            db.session.commit()
            flash('Paper approved successfully')
            return redirect(url_for('dashboard'))
        elif action == 'reject':
            paper.status = 'rejected'
            paper.moderator_id = current_user.id
            history = PaperHistory(
                paper_id=paper.id,
                moderator_id=current_user.id,
                action='reject',
                comment=comment
            )
            db.session.add(history)
            db.session.commit()
            flash('Paper rejected')
            return redirect(url_for('dashboard'))

    return render_template('review_paper.html', paper=paper)


@app.route('/select_paper', methods=['POST'])
@login_required
def select_paper():
    if current_user.role != 'exam_cell':
        return redirect(url_for('dashboard'))

    approved_papers = QuestionPaper.query.filter_by(status='approved').all()

    if len(approved_papers) < 3:
        flash('Need at least 3 approved papers to select one')
        return redirect(url_for('dashboard'))

    selected_paper = random.choice(approved_papers)
    selected_paper.status = 'selected'
    db.session.commit()

    flash(f'Paper "{selected_paper.title}" has been selected for the exam')
    return redirect(url_for('dashboard'))


@app.route('/decrypt_paper/<int:paper_id>', methods=['GET', 'POST'])
@login_required
def decrypt_paper(paper_id):
    if current_user.role not in ['admin', 'exam_cell']:
        return redirect(url_for('dashboard'))

    paper = db.session.get(QuestionPaper, paper_id)
    if paper is None:
        flash('Paper not found')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        # Manual key entry (optional override — auto-decrypt via DB key is preferred)
        manual_key = request.form.get('key', '').strip()
        try:
            key = manual_key.encode('utf-8') if manual_key else _get_key_for_paper(paper)
            encrypted_data = storage_download(paper.encrypted_file_path)
            decrypted_data = decrypt_data(encrypted_data, key)

            basename = os.path.basename(paper.encrypted_file_path.split('?')[0])
            download_name = basename.replace('encrypted_', '')

            return send_file(
                io.BytesIO(decrypted_data),
                as_attachment=True,
                download_name=download_name or 'decrypted_paper.pdf'
            )
        except Exception as e:
            flash(f'Invalid decryption key or error: {str(e)}')

    return render_template('decrypt_paper.html', paper=paper)


@app.route('/select_random_paper', methods=['POST'])
@login_required
def select_random_paper():
    if current_user.role != 'exam_cell':
        flash('Unauthorized access')
        return redirect(url_for('dashboard'))

    subject = request.form.get('subject')
    if not subject:
        flash('Subject is required')
        return redirect(url_for('dashboard'))

    approved_papers = QuestionPaper.query.filter_by(
        status='approved',
        subject=subject
    ).all()

    if not approved_papers:
        flash(f'No approved papers available for {subject.upper()}')
        return redirect(url_for('dashboard'))

    # Reset any previously selected paper for this subject
    QuestionPaper.query.filter_by(
        status='selected',
        subject=subject
    ).update({'status': 'approved'})

    selected_paper = random.choice(approved_papers)
    selected_paper.status = 'selected'
    db.session.commit()

    flash(f'{subject.upper()} Paper "{selected_paper.title}" has been selected for the exam')
    return redirect(url_for('dashboard'))


# ---------------------------------------------------------------------------
# App Entry Point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)