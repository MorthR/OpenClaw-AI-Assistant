import os
import sqlite3
import re
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from skills.registry import SkillRegistry
from skills.email import EmailSkill
from skills.calendar import CalendarSkill

from agent.core import AgentCore
from agent.memory import MemoryManager

load_dotenv()

memory = MemoryManager()
registry = SkillRegistry()

registry.register(EmailSkill())
registry.register(CalendarSkill())

agent = AgentCore(registry=registry, memory=memory, model_name=os.getenv("LLM_MODEL", "deepseek-flash"))

triggered_reminders = set()
pending_notifications = []


def check_schedule_conflict(event_date: str, event_time: str) -> Optional[str]:
    if not os.path.exists("calendar.db"):
        return None
        
    try:
        with sqlite3.connect("calendar.db") as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT title, event_time FROM events WHERE event_date = ?",
                (event_date,)
            )
            existing = cursor.fetchall()
            
            for title, ex_time in existing:
                if ex_time == "All Day" or event_time == "All Day":
                    return f"Conflicts with All-Day event: {title}"
                if ex_time == event_time:
                    return f"Exact time overlap with {title} at {ex_time}"
    except Exception as e:
        print(f"Conflict check error: {e}")
        
    return None


async def auto_reminder_checker():
    while True:
        try:
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M")

            if os.path.exists("calendar.db"):
                with sqlite3.connect("calendar.db") as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT id, title, event_date, event_time, category FROM events WHERE event_date = ? AND event_time = ?",
                        (today_str, time_str)
                    )
                    due_events = cursor.fetchall()
                    
                    for event_id, title, e_date, e_time, cat in due_events:
                        unique_key = f"{event_id}_{e_date}_{e_time}"
                        if unique_key not in triggered_reminders:
                            triggered_reminders.add(unique_key)
                            
                            pending_notifications.append({
                                "id": event_id,
                                "title": title,
                                "time": e_time,
                                "category": str(cat).upper()
                            })
        except Exception as e:
            print(f"Error checking automatic reminders: {e}")

        await asyncio.sleep(10)


@asynccontextmanager
async def lifespan(app: FastAPI):
    reminder_task = asyncio.create_task(auto_reminder_checker())
    yield
    reminder_task.cancel()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

public_env = os.getenv("PUBLIC_URL", "https://neurosis-elated-encrust.ngrok-free.dev")
parsed_url = urlparse(public_env)
BASE_HOST = f"{parsed_url.scheme}://{parsed_url.netloc}" if parsed_url.netloc else "https://neurosis-elated-encrust.ngrok-free.dev"


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
    return {"history": memory.get_recent_history(limit=20)}


@app.get("/")
async def index():
    html_path = os.path.join("static", "index.html")
    if not os.path.exists(html_path):
        return {"error": "index.html not found"}
    return FileResponse(html_path)


@app.get("/calendar/feed.ics")
@app.get("/calendar/download")
def get_ics_feed():
    ics_content = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//OpenClaw AI Personal Agent//EN",
        "X-WR-CALNAME:OpenClaw AI Schedule"
    ]

    if os.path.exists("calendar.db"):
        with sqlite3.connect("calendar.db") as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT title, event_date, event_time, category FROM events")
            for title, e_date, e_time, cat in cursor.fetchall():
                clean_title = re.sub(r'^\s*\[[A-Za-z0-9_-]+\]\s*', '', title).strip()
                ics_content.append("BEGIN:VEVENT")
                ics_content.append(f"SUMMARY:[{str(cat).upper()}] {clean_title}")
                
                if str(e_time).lower() in ["all day", "none", ""]:
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
def get_proactive_suggestions(
    session_id: str = "default_user", 
    email: Optional[str] = None, 
    auth_code: Optional[str] = None,
    is_idle_pulse: bool = False
):
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    tomorrow_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    current_time_str = now.strftime("%H:%M")
    
    upcoming_today_events = []

    if os.path.exists("calendar.db"):
        with sqlite3.connect("calendar.db") as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT title, event_time, category FROM events WHERE event_date = ? ORDER BY event_time ASC",
                (today_str,)
            )
            all_today_events = cursor.fetchall()

            for title, e_time, cat in all_today_events:
                if e_time == "All Day" or e_time >= current_time_str:
                    upcoming_today_events.append((title, e_time, cat))

    important_schedules = []

    if email and auth_code:
        try:
            email_skill = registry.get("email_tool")
            if email_skill:
                mail_res = email_skill.run(
                    {"action": "search", "limit": 20},
                    user_credentials={"email": email, "auth_code": auth_code}
                )
                if mail_res.get("status") == "success":
                    emails = mail_res.get("emails", [])
                    
                    schedule_keywords = ["meeting", "schedule", "call", "due", "appointment", "flight", "invite", "interview", "deadline", "conference"]
                    ignore_keywords = ["ad", "offer", "discount", "sale", "points", "rebate", "newsletter", "promotion", "calendar export", "my calendar"]

                    for m in emails:
                        subj = m.get("subject", "")
                        snip = m.get("snippet", "")
                        text = (subj + " " + snip).lower()
                        
                        if any(kw in text for kw in schedule_keywords) and not any(ikw in text for ikw in ignore_keywords):
                            clean_subj = re.sub(r'^(Re|Fwd):\s*', '', subj, flags=re.IGNORECASE).strip()
                            prop_date = tomorrow_str
                            prop_time = "10:00"
                            conflict_warning = check_schedule_conflict(prop_date, prop_time)
                            
                            important_schedules.append({
                                "title": clean_subj,
                                "date": prop_date,
                                "time": prop_time,
                                "conflict": conflict_warning
                            })
        except Exception as e:
            print(f"Silent auto email check error: {e}")
            
    if is_idle_pulse:
        greeting = "I'm still here whenever you need me! Just let me know if you'd like to organize your upcoming week, log new events, or double-check your inbox."
    else:
        greeting = f"👋 Welcome back! Today is {today_str}.\n"
        if upcoming_today_events:
            event_summary = ", ".join([f"{e[0]} at {e[1]}" for e in upcoming_today_events])
            greeting += f"Here is what's left on your schedule for today: {event_summary}.\n"
        else:
            greeting += "Your schedule looks completely clear for the rest of today!\n"
            
        greeting += "I can help you scan recent emails, organize upcoming meetings, or set up class deadlines."

    inline_choices = []

    if important_schedules:
        greeting += f"\n\nI noticed {len(important_schedules)} potential event(s) in your inbox that might need your attention:"
        for item in important_schedules[:2]:
            conflict_str = f" (Note: {item['conflict']})" if item['conflict'] else ""
            greeting += f"\n• {item['title']} on {item['date']} at {item['time']}{conflict_str}"
        
        greeting += "\n\nWould you like me to go ahead and add these to your calendar?"
        
        for s in important_schedules[:2]:
            inline_choices.append(f"Yes, add: {s['title']}")
        
        inline_choices.append("No, thanks")

    return {
        "greeting": greeting,
        "inline_choices": inline_choices,
        "suggested_chips": [
            "Check recent email details",
            "Recommend schedule from emails",
            "List my calendar"
        ]
    }


@app.get("/api/reminders/pending")
def get_pending_reminders():
    global pending_notifications
    alerts = list(pending_notifications)
    pending_notifications.clear()
    return {"alerts": alerts}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)