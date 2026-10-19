import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime

logging.basicConfig(level=logging.DEBUG)


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "connect-secret-key-change-in-production")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("NEON_DATABASE_URL") or os.environ.get("DATABASE_URL", "sqlite:///connect.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

csrf = CSRFProtect(app)

try:
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
except FileExistsError:
    pass

from utils import has_permission, format_currency, format_date, format_datetime


with app.app_context():
    import models
    db.create_all()

    from models import User, Group
    from werkzeug.security import generate_password_hash

    # Create default group "Pamoja Agencies SHG" if no groups exist
    default_group = Group.query.first()
    if not default_group:
        default_group = Group(
            name='Pamoja Agencies SHG',
            description='Self-Help Group',
            contact_email='pamojaagenciesshg@gmail.com',
            contact_phone='254799466723',
            location='Kenya',
            year_established='2023'
        )
        db.session.add(default_group)
        db.session.commit()
        logging.info("Default group created")

    # Assign existing users without group_id to the default group
    try:
        users_without_group = User.query.filter(
            User.group_id.is_(None),
            User.is_super_admin == False
        ).all()
        for u in users_without_group:
            u.group_id = default_group.id
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error assigning groups: {e}")

    # Create CONNECT super admin if not exists
    super_admin = User.query.filter_by(is_super_admin=True).first()
    if not super_admin:
        existing = User.query.filter_by(username='CONNECT_ADMIN').first()
        if not existing:
            super_admin = User(
                username='CONNECT_ADMIN',
                full_name='CONNECT Administrator',
                email='admin@connect-shg.app',
                phone='0000000000',
                role='Admin',
                password_hash=generate_password_hash('connect@admin2024'),
                is_active=True,
                is_super_admin=True,
                group_id=None
            )
            db.session.add(super_admin)
            db.session.commit()
            logging.info("CONNECT super admin created")

    # Create default group admin if not exists
    admin = User.query.filter_by(username='SALIM TUVA KARISA').first()
    if not admin:
        admin = User(
            username='SALIM TUVA KARISA',
            full_name='Salim Tuva Karisa',
            email='pamojaagenciesshg@gmail.com',
            phone='254799466723',
            role='Admin',
            password_hash=generate_password_hash('34338006tuva'),
            is_active=True,
            group_id=default_group.id
        )
        db.session.add(admin)
        db.session.commit()
        logging.info("Default group admin created")

    try:
        from routes import initialize_default_badges
        initialize_default_badges()
    except Exception as e:
        logging.error(f"Failed to initialize badges: {str(e)}")


# Register from_json as both a Jinja filter AND a context variable
import json as _json
app.jinja_env.filters['from_json'] = lambda s: _json.loads(s) if s else {}


@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))


@app.context_processor
def utility_processor():
    import json
    from flask import session
    from flask_login import current_user

    def from_json(json_string):
        try:
            return json.loads(json_string) if json_string else {}
        except Exception:
            return {}

    current_group = None
    active_group_id = None
    all_groups = []
    unread_notifications = 0
    unread_messages = 0

    try:
        if current_user and current_user.is_authenticated:
            from models import Group
            if current_user.is_super_admin:
                active_group_id = session.get('active_group_id')
                if active_group_id:
                    current_group = Group.query.get(active_group_id)
                all_groups = Group.query.filter_by(is_active=True).order_by(Group.name).all()
            elif current_user.group_id:
                active_group_id = current_user.group_id
                current_group = Group.query.get(current_user.group_id)
            unread_notifications = current_user.get_unread_notifications_count()
            unread_messages = current_user.get_unread_messages_count()
    except Exception:
        pass

    return dict(
        has_permission=has_permission,
        format_currency=format_currency,
        format_date=format_date,
        format_datetime=format_datetime,
        datetime=datetime,
        from_json=from_json,
        current_group=current_group,
        active_group_id=active_group_id,
        all_groups=all_groups,
        unread_notifications=unread_notifications,
        unread_messages=unread_messages,
        app_name='CONNECT'
    )
