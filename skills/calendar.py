import sqlite3
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from .base import BaseSkill

class CalendarSkill(BaseSkill):
    def __init__(self, db_path: str = "calendar.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    event_date TEXT NOT NULL,
                    event_time TEXT DEFAULT 'All Day',
                    category TEXT DEFAULT 'general',
                    is_all_day INTEGER DEFAULT 0,
                    source_email_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(title, event_date, event_time)
                )
            """)
            conn.commit()

    @property
    def name(self) -> str:
        return "calendar_tool"

    @property
    def description(self) -> str:
        return "A tool for managing personal schedule, supporting adding, querying, deduplicating, and conflict checking."

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
                        "description": "Operation type: 'add', 'add_batch', or 'list'",
                        "enum": ["add", "add_batch", "list", "read", "check", "query"]
                    },
                    "title": {
                        "type": "string",
                        "description": "Event title"
                    },
                    "date": {
                        "type": "string",
                        "description": "Date YYYY-MM-DD"
                    },
                    "time": {
                        "type": "string",
                        "description": "Specific time (e.g. '10:00'). Default 'All Day'"
                    },
                    "category": {
                        "type": "string",
                        "description": "Category: 'meeting', 'course', 'entertainment', 'deadline', or 'general'"
                    },
                    "events": {
                        "type": "array",
                        "description": "Array of event objects for batch processing",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "date": {"type": "string"},
                                "time": {"type": "string"},
                                "category": {"type": "string"}
                            }
                        }
                    }
                },
                "required": ["action"]
            }
        }

    def run(self, params: dict, user_credentials: dict = None) -> dict:
        action = str(params.get("action", "list")).lower()
        
        if action in ["read", "query", "get", "check", "show", "search", "list"]:
            target_date = str(params.get("date", "all")).lower()
            return self._list_events(target_date)

        elif action == "add":
            title = params.get("title", "Unnamed Event")
            event_date = params.get("date") or datetime.now().strftime("%Y-%m-%d")
            event_time = params.get("time") or "All Day"
            category = params.get("category", "general")
            return self._add_with_conflict_check(title, event_date, event_time, category)

        elif action == "add_batch":
            events = params.get("events", [])
            results = []
            for item in events:
                res = self._add_with_conflict_check(
                    item.get("title", "Unnamed Event"),
                    item.get("date", datetime.now().strftime("%Y-%m-%d")),
                    item.get("time", "All Day"),
                    item.get("category", "general")
                )
                results.append(res)
            return {"status": "success", "batch_results": results}

        return {"status": "error", "message": f"Unknown action: {action}"}

    def _check_time_conflict(self, event_date: str, event_time: str) -> List[dict]:
        """Check if any event exists on the same date and time."""
        if event_time == "All Day":
            return []
            
        conflicts = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT title, event_time, category FROM events WHERE event_date = ? AND event_time = ?",
                    (event_date, event_time)
                )
                rows = cursor.fetchall()
                for title, e_time, cat in rows:
                    conflicts.append({"title": title, "time": e_time, "category": cat})
        except Exception:
            pass
        return conflicts

    def _add_with_conflict_check(self, title: str, event_date: str, event_time: str, category: str) -> dict:
        conflicts = self._check_time_conflict(event_date, event_time)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id FROM events WHERE title = ? AND event_date = ? AND event_time = ?",
                    (title, event_date, event_time)
                )
                if cursor.fetchone():
                    return {
                        "status": "skipped",
                        "message": f"Event '{title}' on {event_date} at {event_time} already exists."
                    }

                cursor.execute(
                    "INSERT INTO events (title, event_date, event_time, category, is_all_day) VALUES (?, ?, ?, ?, ?)",
                    (title, event_date, event_time, category, 1 if event_time == "All Day" else 0)
                )
                conn.commit()

            res = {
                "status": "success",
                "message": f"Saved event: [{category.upper()}] '{title}' on {event_date} at {event_time}"
            }
            if conflicts:
                res["conflict_warning"] = f"Warning: Event time {event_time} overlaps with existing event '{conflicts[0]['title']}'."
            return res
        except Exception as e:
            return {"status": "error", "message": f"Failed to save event: {str(e)}"}

    def _list_events(self, target_date: str) -> dict:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                if target_date == "all":
                    cursor.execute("SELECT title, event_date, event_time, category FROM events ORDER BY event_date ASC, event_time ASC")
                else:
                    cursor.execute("SELECT title, event_date, event_time, category FROM events WHERE event_date = ? ORDER BY event_time ASC", (target_date,))
                
                rows = cursor.fetchall()
                events = [{"title": r[0], "date": r[1], "time": r[2], "category": r[3]} for r in rows]
                return {"status": "success", "count": len(events), "events": events}
        except Exception as e:
            return {"status": "error", "message": f"Failed to list events: {str(e)}"}