import sqlite3
import bcrypt

DB_PATH = "users.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def register_user(username: str, password: str) -> tuple[bool, str]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cursor.fetchone():
        conn.close()
        return False, "Ce nom d'utilisateur existe déjà."

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    cursor.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, password_hash),
    )
    conn.commit()
    conn.close()
    return True, "Compte créé avec succès."


def login_user(username: str, password: str) -> tuple[bool, str]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return False, "Utilisateur introuvable."

    stored_hash = row[0]
    if isinstance(stored_hash, str):
        stored_hash = stored_hash.encode()
    if bcrypt.checkpw(password.encode(), stored_hash):
        return True, "Connexion réussie."
    return False, "Mot de passe incorrect."


def get_user_id(username: str):
    """Retourne l'id de l'utilisateur (ou None s'il n'existe pas)."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return row[0] if row else None