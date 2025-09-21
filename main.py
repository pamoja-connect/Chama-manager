
from app import app
from routes import *
from app import app, db
import models

with app.app_context():
    db.create_all()
    print("✅ Database tables created or already exist.")

#if __name__ == '__main__':
   # app.run(host='0.0.0.0', port=5000, debug=True)
