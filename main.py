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

memory = MemoryManager()
registry = SkillRegistry()

registry.register(EmailSkill())
registry.register(CalendarSkill())

agent = AgentCore(registry=registry, memory=memory, model_name="qwen2.5:1.5b")

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