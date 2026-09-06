# OpenClaw Assistant

OpenClaw Assistant is a lightweight, local LLM-powered agent framework built on FastAPI and Ollama. Designed for multi-skill orchestration, it enables seamless coordination between remote services (e.g., IMAP/SMTP email) and local databases (e.g., SQLite calendar management) while addressing temporal awareness and context leakage in multi-turn agent execution.

## System Architecture

The project adopts a modular agent pipeline architecture:

- **Agent Core (`agent/core.py`)**: Manages intent routing, tool execution, and response synthesis via Qwen2.5.
- **Skill Registry (`skills/registry.py`)**: Provides dynamic skill registration, schema extraction, and execution dispatching.
- **Memory Manager (`agent/memory.py`)**: Stores and retrieves short-term conversational history.
- **Skill Extensions (`skills/`)**:
  - `EmailSkill`: Encapsulates IMAP/SMTP protocols for searching and sending emails.
  - `CalendarSkill`: Provides CRUD operations for local schedule management using SQLite.

```text
OpenClaw-Assistant/
├── agent/
│   ├── core.py           # LLM decision loop and prompt engineering
│   └── memory.py         # Conversation history management
├── skills/
│   ├── base.py           # Abstract Base Skill class
│   ├── registry.py       # Centralized skill registry
│   ├── qq_email.py       # Email skill implementation
│   └── calendar_tool.py  # SQLite-backed calendar skill implementation
├── main.py               # FastAPI entry point
└── requirements.txt      # Project dependencies
