import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from skills.registry import SkillRegistry
from skills.qq_email import EmailSkill
from skills.calendar import CalendarSkill

from agent.core import AgentCore
from agent.memory import MemoryManager

QQ_USER = "519656964@qq.com"
QQ_PASS = "xavrsazgrpuvcbaf"

memory = MemoryManager()
registry = SkillRegistry()

registry.register(EmailSkill(username=QQ_USER, password=QQ_PASS))
registry.register(CalendarSkill())

agent = AgentCore(registry=registry, memory=memory)

#Initialize FastAPI app and mount static files
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

class ChatRequest(BaseModel):
    message: str

@app.post("/api/chat")
def chat(req: ChatRequest):
    #Save the conversation to memory
    response_data = agent.process(req.message)
    return response_data

@app.get("/api/history")
def get_history():
    """Load local chat history"""
    return {"history": memory.get_recent_history(limit=20)}

@app.get("/", response_class=HTMLResponse)
def index():
    """Return the HTML frontend page"""
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()