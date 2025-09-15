
import os
from app import app, db
from models import *
from werkzeug.security import generate_password_hash

def migrate_database():
    """Migrate database schema to add missing columns."""
    with app.app_context():
        print("Starting database migration...")
        
        # Drop all tables with cascade to handle dependencies
        try:
            db.engine.execute('DROP SCHEMA public CASCADE')
            db.engine.execute('CREATE SCHEMA public')
        except:
            # Fallback to regular drop_all
            db.drop_all()
        
        db.create_all()
        
        # Recreate default admin user
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
            print("Default admin user recreated")
        
        print("Database migration completed successfully!")

if __name__ == '__main__':
    migrate_database()
