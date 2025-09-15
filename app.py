import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configure upload folder
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///pamoja.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

# Initialize CSRF protection
csrf = CSRFProtect(app)

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Import actual helper functions
from utils import has_permission, format_currency, format_date, format_datetime


with app.app_context():
    # Import models to ensure tables are created
    import models
    db.create_all()

    # Create default admin if not exists
    from models import User
    from werkzeug.security import generate_password_hash

    admin = User.query.filter_by(username='SALIM TUVA KARISA').first()
    if not admin:
        admin = User(
            username='SALIM TUVA KARISA',
            full_name='Salim Tuva Karisa',
            email='pamojaagenciesshg@gmail.com',
            phone='254799466723',
            role='Admin',
            password_hash=generate_password_hash('34338006tuva'),
            is_active=True
        )
        db.session.add(admin)
        db.session.commit()
        logging.info("Default admin user created")

    # Initialize default badges
    try:
        from routes import initialize_default_badges
        initialize_default_badges()
        logging.info("Default badges initialized")
    except Exception as e:
        logging.error(f"Failed to initialize badges: {str(e)}")

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))

@app.context_processor
def utility_processor():
    import json
    def from_json(json_string):
        try:
            return json.loads(json_string) if json_string else {}
        except:
            return {}
    return dict(has_permission=has_permission, format_currency=format_currency, format_date=format_date, format_datetime=format_datetime, datetime=datetime, from_json=from_json)
