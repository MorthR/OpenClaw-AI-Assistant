import os
from typing import Optional
import anyio
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from skills.registry import SkillRegistry
from skills.email import EmailSkill
from skills.calendar import CalendarSkill

from agent.core import AgentCore
from agent.memory import MemoryManager

from fastapi.responses import Response

memory = MemoryManager()
registry = SkillRegistry()

registry.register(EmailSkill())
registry.register(CalendarSkill())

agent = AgentCore(registry=registry, memory=memory, model_name="deepseek-flash")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default_user"
    email: Optional[str] = None
    auth_code: Optional[str] = None

@app.post("/api/chat")
async def chat(req: ChatRequest):
    credentials = {
        "email": req.email,
        "auth_code": req.auth_code
    } if req.email and req.auth_code else None

    return StreamingResponse(
        agent.process_stream(
            user_prompt=req.message, 
            session_id=req.session_id,
            user_credentials=credentials
        ),
        media_type="text/plain; charset=utf-8"
    )

@app.get("/api/history")
def get_history():
    """Load local chat history"""
    return {"history": memory.get_recent_history(limit=20)}

@app.get("/")
async def index():
    """Return the HTML frontend page"""
    html_path = os.path.join("static", "index.html")
    if not os.path.exists(html_path):
        return {"error": "index.html not found under static/ directory"}
    return FileResponse(html_path)

from fastapi.responses import Response

@app.get("/calendar/feed.ics")
def get_ics_feed():
    """Export standard iCalendar (.ics) feed in English."""
    import sqlite3
    import re
    from datetime import datetime

    ics_content = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//OpenClaw AI Personal Agent//EN",
        "X-WR-CALNAME:OpenClaw AI Schedule"
    ]

    with sqlite3.connect("calendar.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title, event_date, event_time, category FROM events")
        rows = cursor.fetchall()
        for title, e_date, e_time, cat in rows:
            clean_title = re.sub(r'^\s*\[[A-Za-z0-9_-]+\]\s*', '', title).strip()
            ics_content.append("BEGIN:VEVENT")
            ics_content.append(f"SUMMARY:[{cat.upper()}] {clean_title}")
            
            if e_time in ["All Day"]:
                dt_str = e_date.replace("-", "")
                ics_content.append(f"DTSTART;VALUE=DATE:{dt_str}")
            else:
                try:
                    dt = datetime.strptime(f"{e_date} {e_time}", "%Y-%m-%d %H:%M")
                    dt_str = dt.strftime("%Y%m%dT%H%M%S")
                    ics_content.append(f"DTSTART:{dt_str}")
                except Exception:
                    dt_str = e_date.replace("-", "")
                    ics_content.append(f"DTSTART;VALUE=DATE:{dt_str}")

            ics_content.append("END:VEVENT")

    ics_content.append("END:VCALENDAR")
    return Response(content="\r\n".join(ics_content), media_type="text/calendar")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)