import sys, getpass
from app import app, db
from models import User
from werkzeug.security import generate_password_hash

if len(sys.argv) != 2:
    print("Usage: python reset_member_password.py 'USERNAME'")
    raise SystemExit
with app.app_context():
    u = User.query.filter(db.func.lower(User.username) == sys.argv[1].lower()).first()
    if not u:
        print("No such username")
        raise SystemExit
    pw = getpass.getpass("New password: ")
    if len(pw) < 8 or pw != getpass.getpass("Confirm: "):
        print("Too short (min 8) or the entries do not match. Nothing changed.")
        raise SystemExit
    u.password_hash = generate_password_hash(pw)
    db.session.commit()
    print("Password reset for", u.username, "| role:", u.role)
