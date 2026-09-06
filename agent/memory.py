import sqlite3
from datetime import datetime

class MemoryManager:
    def __init__(self, db_path: str = "assistant_memory.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the database table structure"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def add_message(self, role: str, content: str):
        """Save a chat message to the database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO chat_history (role, content) VALUES (?, ?)",
                (role, content)
            )
            conn.commit()

    def get_recent_history(self, limit: int = 10) -> list:
        """Get the recent chat history"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT role, content FROM chat_history ORDER BY id DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            #Reverse the order to maintain chronological flow
            return [{"role": r[0], "content": r[1]} for r in reversed(rows)]