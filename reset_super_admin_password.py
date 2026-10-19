"""Securely reset the CONNECT platform super-admin password from Replit Shell.

Run with: python reset_super_admin_password.py
The password is entered with terminal echo disabled and is never printed.
"""

from getpass import getpass
import sys

from werkzeug.security import generate_password_hash

from app import app, db
from models import User


MIN_PASSWORD_LENGTH = 12


def prompt_for_password():
    for attempt in range(3):
        password = getpass("New password (input hidden): ")
        confirmation = getpass("Confirm new password: ")

        if password != confirmation:
            print("The passwords did not match. Try again.")
            continue
        if len(password) < MIN_PASSWORD_LENGTH:
            print(f"Use at least {MIN_PASSWORD_LENGTH} characters. Try again.")
            continue
        return password

    raise ValueError("Password entry failed after three attempts.")


def choose_super_admin(users):
    if len(users) == 1:
        return users[0]

    print("Multiple active CONNECT super-admin accounts were found:")
    for index, user in enumerate(users, start=1):
        print(f"{index}. {user.username} — {user.full_name}")

    while True:
        selected = input("Enter the number for the account to reset: ").strip()
        if selected.isdigit() and 1 <= int(selected) <= len(users):
            return users[int(selected) - 1]
        print("Choose one of the listed numbers.")


def main():
    with app.app_context():
        users = (
            User.query.filter_by(is_super_admin=True, is_active=True)
            .order_by(User.username)
            .all()
        )
        if not users:
            print("No active CONNECT super-admin account was found; no changes were made.")
            return 1

        account = choose_super_admin(users)
        print(f"Resetting the password for {account.username} ({account.full_name}).")
        try:
            password = prompt_for_password()
            account.password_hash = generate_password_hash(password)
            db.session.commit()
        except (EOFError, KeyboardInterrupt):
            db.session.rollback()
            print("\nPassword reset cancelled; no changes were made.")
            return 1
        except ValueError as error:
            db.session.rollback()
            print(f"{error} No changes were made.")
            return 1
        except Exception as error:
            db.session.rollback()
            print(f"Password reset failed ({type(error).__name__}); no changes were committed.")
            return 1
        finally:
            # Drop our reference as soon as the transaction completes.
            if "password" in locals():
                del password

    print("Password reset successfully. Sign in with the new password.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
