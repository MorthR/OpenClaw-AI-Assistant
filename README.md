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
│   ├── email.py          # Email skill implementation
│   └── calendar.py       # SQLite-backed calendar skill implementation
├── main.py               # FastAPI entry point
└── requirements.txt      # Project dependencies
```

## Key Technical Solutions

### 1. Temporal Baseline Alignment

Standard LLM implementations frequently suffer from temporal hallucinations when processing relative time references (e.g., "today", "tomorrow"). **OpenClaw Assistant** dynamically injects host system timestamps into the system prompt, providing an explicit temporal anchor to ensure deterministic date calculations (`YYYY-MM-DD`).

### 2. Context Isolation & De-pollution

To prevent cross-domain context leakage during tool execution summaries (e.g., carrying prior email query results into calendar tasks), the framework employs isolated prompt templates during the synthesis phase, restricting the model's focus strictly to the active task payload.

## Prerequisites

* **Python**: `3.10+`
* **Ollama**: Installed and running locally with the `qwen2.5:7b` model

## Installation & Setup

1. **Clone the repository:**

   ```bash
   git clone https://github.com/your-username/OpenClaw-Assistant.git
   cd OpenClaw-Assistant
   ```

2. **Create and activate a virtual environment:**

   ```bash
   python -m venv venv
   
   # On Windows
   venv\Scripts\activate
   
   # On Linux/macOS
   source venv/bin/activate
   ```

3. **Install required dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application server:**

   ```bash
   uvicorn main:app --reload
   ```