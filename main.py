from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os

from skills.registry import SkillRegistry
from skills.mock_email import MockEmailSkill
from agent.core import AgentCore
from agent.memory import MemoryManager

from fastapi.staticfiles import StaticFiles
from skills.qq_email import EmailSkill

QQ_USER = "519656964@qq.com"
QQ_PASS = "xavrsazgrpuvcbaf"

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

#Initializing Components
registry = SkillRegistry()
registry.register(EmailSkill(username=QQ_USER, password=QQ_PASS))
agent = AgentCore(registry=registry)
memory = MemoryManager()

class ChatRequest(BaseModel):
    message: str

@app.post("/api/chat")
def chat(req: ChatRequest):
    #1. Record user message
    memory.add_message("user", req.message)

    #2. Agent processing
    response_data = agent.process(req.message)

    #3. Record assistant message
    if response_data.get("type") == "skill_executed":
        bot_msg = f"Executed skill 【{response_data['skill']}】, Result: {response_data['data']}"
    else:
        bot_msg = response_data.get("text", "")

    memory.add_message("assistant", bot_msg)
    return response_data

@app.get("/api/history")
def get_history():
    """Get the local chat history"""
    return {"history": memory.get_recent_history(limit=20)}

@app.get("/", response_class=HTMLResponse)
def index():
    """Return the HTML frontend page"""
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()