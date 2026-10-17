import sqlite3

DB_PATH = "chat_history.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Crée les tables si elles n'existent pas (et ajoute user_id si besoin)."""
    conn = get_connection()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            title      TEXT NOT NULL DEFAULT 'Nouvelle conversation',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role            TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
            content         TEXT NOT NULL,
            created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);

        CREATE TABLE IF NOT EXISTS projects (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            name       TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);
        """
    )
    # Migration : ancienne base créée sans la colonne user_id
    colonnes = [r["name"] for r in conn.execute("PRAGMA table_info(conversations)")]
    if "user_id" not in colonnes:
        conn.execute("ALTER TABLE conversations ADD COLUMN user_id INTEGER")
    # Migration : conversations rattachées à un projet (NULL = conversation générale)
    if "project_id" not in colonnes:
        conn.execute("ALTER TABLE conversations ADD COLUMN project_id INTEGER")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_project ON conversations(project_id)")
    conn.commit()
    conn.close()


def create_conversation(user_id, title="Nouvelle conversation", project_id=None):
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO conversations (user_id, title, project_id) VALUES (?, ?, ?)",
        (user_id, title, project_id),
    )
    conn.commit()
    conv_id = cur.lastrowid
    conn.close()
    return conv_id


def list_conversations(user_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, title, created_at, project_id FROM conversations WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return rows


def rename_conversation(conversation_id, title, user_id):
    conn = get_connection()
    conn.execute(
        "UPDATE conversations SET title = ? WHERE id = ? AND user_id = ?",
        (title, conversation_id, user_id),
    )
    conn.commit()
    conn.close()


def delete_conversation(conversation_id, user_id):
    conn = get_connection()
    conn.execute(
        "DELETE FROM conversations WHERE id = ? AND user_id = ?",
        (conversation_id, user_id),
    )
    conn.commit()
    conn.close()


def add_message(conversation_id, role, content):
    conn = get_connection()
    conn.execute(
        "INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)",
        (conversation_id, role, content),
    )
    conn.commit()
    conn.close()


def get_messages(conversation_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id",
        (conversation_id,),
    ).fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


# =====================================================================
# PROJETS
# =====================================================================
def create_project(user_id, name):
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO projects (user_id, name) VALUES (?, ?)", (user_id, name)
    )
    conn.commit()
    project_id = cur.lastrowid
    conn.close()
    return project_id


def list_projects(user_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, created_at FROM projects WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return rows


def rename_project(project_id, name, user_id):
    conn = get_connection()
    conn.execute(
        "UPDATE projects SET name = ? WHERE id = ? AND user_id = ?",
        (name, project_id, user_id),
    )
    conn.commit()
    conn.close()


def delete_project(project_id, user_id):
    """Supprime le projet ET toutes ses conversations (les messages partent en cascade)."""
    conn = get_connection()
    conn.execute(
        "DELETE FROM conversations WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    )
    conn.execute(
        "DELETE FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id)
    )
    conn.commit()
    conn.close()