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
├── config/
│   └── logger.py         # Application log setup
├── skills/
│   ├── base.py           # Abstract Base Skill class
│   ├── registry.py       # Centralized skill registry
│   ├── email.py          # Email skill implementation
│   └── calendar.py       # SQLite-backed calendar skill implementation
├── static/
│   ├── index.html        # Web interface layout
│   └── style.css         # UI styles and stylesheets
├── main.py               # FastAPI entry point
├── README.md             # Project documentation
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
   git clone https://github.com/MorthR/OpenClaw-Assistant.git
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

## User Email Setup Guide

To allow the AI Agent to safely access and manage your mailbox (search emails, send messages), you need to provide an App-Specific Password instead of your primary login password.

### Step 1: Obtain App Password based on your email provider

**Gmail**
  1. Go to your Google Account Settings.
  2. Enable 2-Step Verification in the Security tab.
  3. Search for App Passwords, generate a new password named `OpenClaw Agent`.
  4. Copy the generated 16-character code.

**QQ Mail**
  1. Log in to QQ Mail web page, go to **Settings** > **Accounts**.
  2. Scroll down to **POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV Services**.
  3. Enable **POP3/SMTP Service** or **IMAP/SMTP Service**.
  4. Follow instructions to send SMS and receive your 16-character Authorization Code.

**Outlook / Office365**
  1. Log in to your Microsoft Account Security page.
  2. Select **Advanced security options** > **App passwords** > **Create a new app password**.

### Step 2: Configure Credentials in OpenClaw

1. Open the OpenClaw web portal.
2. Click on the **Settings** icon in the top right / navigation menu.
3. Fill in your **Email Address** and the **App Password / Authorization Code** generated in Step 1.
4. Click **Save & Test Connection**.
