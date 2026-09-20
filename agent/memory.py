import sqlite3

class MemoryManager:
    def __init__(self, db_path="memory.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT DEFAULT 'default_user',
                    category TEXT DEFAULT 'general',
                    role TEXT,
                    content TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            try:
                cursor.execute("ALTER TABLE history ADD COLUMN category TEXT DEFAULT 'general'")
            except sqlite3.OperationalError:
                pass  # Column already exists
            conn.commit()

    def add_record(self, session_id: str, role: str, content: str, category: str = "general"):
        """Insert a chat record with domain category tagging."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO history (session_id, role, content, category) VALUES (?, ?, ?, ?)",
                (session_id, role, content, category)
            )
            conn.commit()
            
    def add_message(self, role: str, content: str, session_id: str = "default_user", category: str = "general"):
        self.add_record(session_id, role, content, category)

    def get_recent_history(self, session_id: str = "default_user", category: str = None, limit: int = 6) -> list:
        """
        Retrieve recent history. 
        If category is provided, retrieves history filtered by that domain or 'general'.
        If category is None, retrieves standard sequential history.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if category:
                cursor.execute(
                    """
                    SELECT role, content FROM history 
                    WHERE session_id = ? AND (category = ? OR category = 'general')
                    ORDER BY id DESC LIMIT ?
                    """,
                    (session_id, category, limit)
                )
            else:
                cursor.execute(
                    "SELECT role, content FROM history WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                    (session_id, limit)
                )
            rows = cursor.fetchall()
            return [{"role": row[0], "content": row[1]} for row in reversed(rows)]