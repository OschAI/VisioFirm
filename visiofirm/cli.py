"""
VisioFirm command-line interface — user administration.

Usage:
    visiofirm                                  start the web app
    visiofirm users                           list all users
    visiofirm <username|email> set-pswd <pw>  reset a user's password
    visiofirm -V | --version                  print version
    visiofirm -h | --help                     show this help
"""

import sys
import sqlite3

from visiofirm.config import get_db_path
from visiofirm.models.user import (
    init_db,
    update_user,
    get_user_by_username,
    get_user_by_email,
)

USAGE = __doc__


def list_users():
    init_db()
    with sqlite3.connect(get_db_path()) as conn:
        rows = conn.execute(
            "SELECT id, username, email, first_name, last_name, company, api_key "
            "FROM users ORDER BY id"
        ).fetchall()

    if not rows:
        print("No users found.")
        return 0

    headers = ["ID", "Username", "Email", "First name", "Last name", "Company", "API key"]
    table = [headers] + [[str(c) if c is not None else "" for c in row] for row in rows]
    widths = [max(len(row[i]) for row in table) for i in range(len(headers))]
    for row in table:
        print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip())
    return 0


def set_password(identifier, new_password):
    user = get_user_by_username(identifier)
    if user is None:
        user = get_user_by_email(identifier)
    if user is None:
        print(f"Error: no user found for '{identifier}' (tried username and email).",
              file=sys.stderr)
        return 1

    if update_user(user[0], {"password": new_password}):
        print(f"Password updated for '{user[1]}' ({user[5]}).")
        return 0

    print("Error: could not update password.", file=sys.stderr)
    return 1


def main(argv=None):
    args = list(argv) if argv is not None else sys.argv[1:]

    if args in (["-h"], ["--help"]):
        print(USAGE)
        return 0
    if args == ["users"]:
        return list_users()
    if args and args[0] == "users":
        print(f"Error: unexpected arguments after 'users': {' '.join(args[1:])}", file=sys.stderr)
        return 2
    if "set-pswd" in args:
        if len(args) != 3:
            print("Error: expected 'visiofirm <username|email> set-pswd <newpassword>'.", file=sys.stderr)
            return 2
        return set_password(args[0], args[2])

    # Everything else (no args, -V/--version, server invocation) launches the web app.
    from run import main as run_main
    return run_main()


if __name__ == "__main__":
    sys.exit(main())
