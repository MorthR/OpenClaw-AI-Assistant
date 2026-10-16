import os
import sqlite3
import re
from datetime import datetime
from typing import Optional
import anyio
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from skills.registry import SkillRegistry
from skills.email import EmailSkill
from skills.calendar import CalendarSkill

from agent.core import AgentCore
from agent.memory import MemoryManager

memory = MemoryManager()
registry = SkillRegistry()

registry.register(EmailSkill())
registry.register(CalendarSkill())

agent = AgentCore(registry=registry, memory=memory, model_name="deepseek-flash")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

PUBLIC_FEED_URL = "http://127.0.0.1:8000/calendar/feed.ics"

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

@app.on_event("startup")
def setup_public_tunnel():
    global PUBLIC_FEED_URL
    try:
        from pyngrok import ngrok
        token = os.getenv("NGROK_AUTHTOKEN")
        if token:
            ngrok.set_auth_token(token)
            domain = os.getenv("NGROK_DOMAIN", "neurosis-elated-encrust.ngrok-free.dev")
            tunnel = ngrok.connect(8000, domain=domain)
            PUBLIC_FEED_URL = tunnel.public_url + "/calendar/feed.ics"
            print(f"========== PUBLIC CALENDAR FEED LOADED ==========")
            print(f"URL: {PUBLIC_FEED_URL}")
            print(f"==================================================")
    except Exception as e:
        print(f"Tunnel auto-start fallback to local: {e}")

@app.get("/calendar/feed.ics")
@app.get("/calendar/download")
def get_ics_feed():
    ics_content = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//OpenClaw AI Personal Agent//EN",
        "X-WR-CALNAME:OpenClaw AI Schedule"
    ]

    with sqlite3.connect("calendar.db") as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title, event_date, event_time, category FROM events")
        for title, e_date, e_time, cat in cursor.fetchall():
            clean_title = re.sub(r'^\s*\[[A-Za-z0-9_-]+\]\s*', '', title).strip()
            ics_content.append("BEGIN:VEVENT")
            ics_content.append(f"SUMMARY:[{cat.upper()}] {clean_title}")
            
            if e_time in ["All Day"]:
                ics_content.append(f"DTSTART;VALUE=DATE:{e_date.replace('-', '')}")
            else:
                try:
                    dt = datetime.strptime(f"{e_date} {e_time}", "%Y-%m-%d %H:%M")
                    ics_content.append(f"DTSTART:{dt.strftime('%Y%m%dT%H%M%S')}")
                except Exception:
                    ics_content.append(f"DTSTART;VALUE=DATE:{e_date.replace('-', '')}")
            ics_content.append("END:VEVENT")

    ics_content.append("END:VCALENDAR")
    return Response(
        content="\r\n".join(ics_content),
        media_type="text/calendar",
        headers={"Content-Disposition": "attachment; filename=calendar_export.ics"}
    )

@app.get("/api/proactive-suggestions")
def get_proactive_suggestions(session_id: str = "default_user"):
    import sqlite3
    from datetime import date

    today_str = date.today().isoformat()

    with sqlite3.connect("calendar.db") as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT title, event_time, category FROM events WHERE event_date = ? ORDER BY event_time ASC",
            (today_str,)
        )
        today_events = cursor.fetchall()

    if today_events:
        event_summary = ", ".join([f"{e[0]} at {e[1]}" for e in today_events])
        greeting = f"Good morning! Here is your schedule for today ({today_str}): {event_summary}."
    else:
        greeting = f"Hello! You have no events scheduled for today ({today_str})."

    return {
        "greeting": greeting,
        "suggested_chips": [
            "Record a new meeting",
            "Add a class schedule",
            "Log an entertainment activity",
            "Export my full calendar"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)