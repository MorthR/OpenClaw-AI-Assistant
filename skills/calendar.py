import sqlite3
from datetime import datetime, timedelta
from .base import BaseSkill

class CalendarSkill(BaseSkill):
    def __init__(self, db_path: str = "calendar.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the calendar database table"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    event_date TEXT NOT NULL, -- 格式: YYYY-MM-DD
                    event_time TEXT DEFAULT '全天',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    @property
    def name(self) -> str:
        return "calendar_tool"

    @property
    def description(self) -> str:
        return "A tool for managing personal schedule, supporting adding new events and querying today's or specified date's event list"

    @property
    def schema(self) -> dict:
        return {
            "name": "calendar_tool",
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Operation type: 'add' for adding events, 'list' for querying events",
                        "enum": ["add", "list"]
                    },
                    "title": {
                        "type": "string",
                        "description": "Event title/subject, e.g., 'FYP Mid-term Defense'"
                    },
                    "date": {
                        "type": "string",
                        "description": "Date, format: YYYY-MM-DD, e.g., '2026-09-06'. If 'today' or unspecified, defaults to today"
                    },
                    "time": {
                        "type": "string",
                        "description": "Specific time point, e.g., '14:30' or '2 PM'"
                    }
                },
                "required": ["action"]
            }
        }

    def run(self, params: dict) -> dict:
        action = params.get("action", "list")
        
        raw_date = params.get("date", "today")
        if not raw_date or raw_date.lower() in ["today", "今天"]:
            target_date = datetime.now().strftime("%Y-%m-%d")
        elif raw_date.lower() in ["tomorrow", "明天"]:
            target_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            target_date = raw_date

        if action == "add":
            title = params.get("title", "Unnamed Event")
            time_str = params.get("time", "All Day")
            return self._add_event(title, target_date, time_str)

        elif action == "list":
            return self._list_events(target_date)

        return {"status": "error", "message": f"Unknown action: {action}"}

    def _add_event(self, title: str, event_date: str, event_time: str) -> dict:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO events (title, event_date, event_time) VALUES (?, ?, ?)",
                    (title, event_date, event_time)
                )
                conn.commit()
            return {
                "status": "success",
                "message": f"Success to add event: [{event_date} {event_time}] {title}"
            }
        except Exception as e:
            return {"status": "error", "message": f"Fail to add event: {str(e)}"}

    def _list_events(self, target_date: str) -> dict:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT title, event_time FROM events WHERE event_date = ? ORDER BY id ASC",
                    (target_date,)
                )
                rows = cursor.fetchall()
                events = [{"title": r[0], "time": r[1]} for r in rows]
                return {
                    "status": "success",
                    "date": target_date,
                    "count": len(events),
                    "events": events
                }
        except Exception as e:
            return {"status": "error", "message": f"Fail to list events: {str(e)}"}