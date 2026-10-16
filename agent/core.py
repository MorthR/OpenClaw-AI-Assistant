import json
import datetime
import time
import httpx
import inspect
import os
import anyio
from urllib.parse import urlparse
from typing import AsyncGenerator
from dotenv import load_dotenv
from skills.registry import SkillRegistry
from agent.memory import MemoryManager
from config.logger import logger

load_dotenv()

api_key = os.getenv("LLM_API_KEY", "")

public_env = os.getenv("PUBLIC_URL", "https://neurosis-elated-encrust.ngrok-free.dev")
parsed_url = urlparse(public_env)
BASE_HOST = f"{parsed_url.scheme}://{parsed_url.netloc}" if parsed_url.netloc else "https://neurosis-elated-encrust.ngrok-free.dev"

if not api_key:
    print("LLM_API_KEY is empty. Please check your .env file.")
else:
    print(f"LLM_API_KEY loaded successfully (Length: {len(api_key)}).")


class AgentCore:
    def __init__(
        self, 
        registry: SkillRegistry, 
        memory: MemoryManager, 
        model_name: str = os.getenv("LLM_MODEL", "deepseek-flash"),
        base_url: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1"),
        api_key: str = os.getenv("LLM_API_KEY", "")
    ):
        self.registry = registry
        self.memory = memory
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")

        if not api_key:
            logger.warning("LLM_API_KEY not detected. Please check your .env configuration.")
        else:
            logger.info(f"LLM key loaded successfully. Using model: {self.model_name}")

        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

    async def process_stream(
        self, 
        user_prompt: str, 
        session_id: str = "default_user", 
        user_credentials: dict = None
    ) -> AsyncGenerator[str, None]:
        start_time = time.time()
        logger.info(f"Received user prompt: '{user_prompt}' [Session: {session_id}]")

        now = datetime.datetime.now()
        current_date_str = now.strftime("%Y-%m-%d")
        current_time_str = now.strftime("%H:%M")
        weekday_str = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][now.weekday()]

        available_skills = self.registry.list_skills()

        history_records = self.memory.get_recent_history(session_id=session_id, limit=6, category=None)
        history_text = ""
        if history_records:
            history_text = "[Chat History]:\n" + "\n".join([f"{item['role']}: {item['content']}" for item in history_records]) + "\n\n"

        system_prompt = f"""You are an autonomous personal assistant (OpenClaw AI).
        [Current Time Baseline]:
        - Today's Date is: {current_date_str} ({weekday_str}), Current Time is: {current_time_str}.

        Available tools:
        {json.dumps(available_skills, ensure_ascii=False, indent=2)}

        {history_text}CRITICAL ROUTING & INTENT RULES:
        1. NO MECHANICAL MARKDOWN SYMBOLS: NEVER use Markdown headers (`#`, `##`), bold markers (`**`), or complex Markdown tables in text responses. Keep language natural, conversational, and user-friendly.
        2. EXPANDED SCHEDULE SCOPE: Detect and extract ANY schedule items (Meetings, Class/Course changes, Deadlines, Travel/Flight bookings, Entertainment/Concerts, Bills/Reminders).
        3. EXTENDED EMAIL SEARCH SCOPE (LAST 30 DAYS): When reading/checking emails, pass `limit: 20` to `email_tool`.
        4. FILTER SYSTEM EXPORTS & SPAM: Completely ignore email subjects like "My Calendar Export" or general marketing newsletters when recommending schedule items.
        5. RELATIVE TIME PARSING: Convert relative times ("tomorrow 2pm", "next Wednesday") to standard YYYY-MM-DD and HH:MM based on baseline ({current_date_str}).
        6. EMAIL ROUTING: If user asks to check, read, search, or inspect emails, set "tool" to "email_tool" with `action: "search"` and `limit: 20`.
        7. CALENDAR ROUTING: If user asks to view/add/update/export schedule items, set "tool" to "calendar_tool".

        EXPECTED OUTPUT FORMAT (JSON):
        For Single Tool Execution:
        {{
            "tool": "email_tool",
            "parameters": {{"action": "search", "limit": 20}},
            "suggested_chips": ["Recommend schedule from emails", "List my calendar"],
            "response": null
        }}

        For Calendar Execution:
        {{
            "tool": "calendar_tool",
            "parameters": {{"action": "add", "title": "AI Course Midterm", "date": "2026-10-20", "time": "14:00", "category": "course"}},
            "suggested_chips": ["List my calendar", "Check recent email details"],
            "response": null
        }}

        For Direct Chat:
        {{
            "tool": null,
            "parameters": null,
            "suggested_chips": ["Check recent email details", "List my calendar"],
            "response": "Hello! How can I help manage your schedule or check your emails today?"
        }}
        """

        full_assistant_reply = ""

        async with httpx.AsyncClient(timeout=60.0) as client:
            logger.info("Sending request to API for decision...")
            
            try:
                decision_response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json={
                        "model": self.model_name,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "temperature": 0.1,
                        "response_format": {"type": "json_object"}
                    }
                )
                res_json = decision_response.json()
                
                if "choices" not in res_json:
                    logger.error(f"API Error Response: {res_json}")
                    yield f"API Error: {res_json}"
                    return

                raw_output = res_json["choices"][0]["message"]["content"]
                logger.info(f"LLM Raw Output: {raw_output}")

            except Exception as e:
                logger.error(f"Failed to communicate with LLM API: {str(e)}")
                yield f"Error: Unable to connect to LLM service ({str(e)})"
                return

            try:
                parsed = json.loads(raw_output)
            except Exception as e:
                logger.error(f"Failed to parse JSON output: {raw_output}")
                parsed = {"tool": None, "response": raw_output}
            
            tool_name = parsed.get("tool") or parsed.get("action") or parsed.get("function")
            if tool_name and str(tool_name).lower() in ["none", "null"]:
                tool_name = None

            logger.info(f"Decision output parsed. Selected Tool: {tool_name}")

            if tool_name and (skill := self.registry.get(tool_name)):
                tool_start = time.time()
                params = parsed.get("parameters") or parsed.get("params") or {}
                logger.info(f"Executing skill [{tool_name}] with params: {params}")
                
                sig = inspect.signature(skill.run)
                if "user_credentials" in sig.parameters:
                    execution_res = await anyio.to_thread.run_sync(skill.run, params, user_credentials)
                else:
                    execution_res = await anyio.to_thread.run_sync(skill.run, params)

                logger.info(f"Skill [{tool_name}] execution completed in {time.time() - tool_start:.2f}s. Result: {execution_res}")
                
                download_link = f"{BASE_HOST}/calendar/download"
                
                summary_prompt = f"""You are a warm, helpful personal AI assistant.
                Today's date is {current_date_str} ({weekday_str}), and current time is {current_time_str}.
                User request: "{user_prompt}"
                Tool [{tool_name}] execution result:
                {json.dumps(execution_res, ensure_ascii=False)}

                STRICT TEXT FORMATTING INSTRUCTIONS:
                1. DO NOT use markdown headers like `#` or `##`.
                2. DO NOT use markdown bold stars like `**`.
                3. DO NOT output complex Markdown tables.
                4. Keep the tone warm, natural, and human-like.

                RESPONSE GUIDELINES BY SCENARIO:

                Scenario A: Check recent email details
                - First, summarize the general types of emails received (e.g. "I reviewed your recent inbox messages. Most of them are bank notifications, service updates, and subscription newsletters.").
                - Then list 4-5 relevant messages in plain bullet points using this exact simple format:
                • Sender: Subject (Date)
                - End with a friendly, natural follow-up question.

                Scenario B: Recommend schedule from emails
                - If no clear meetings, classes, or flights are found, state naturally: "I scanned your recent emails, but couldn't find any explicit meetings, class schedules, or deadlines."
                - Do not create fake schedule items out of bank transactions or marketing offers.
                - Offer to help add any custom event manually.

                Scenario C: List my calendar
                - Show clean upcoming schedule lines: YYYY-MM-DD | HH:MM | Title
                - Omit past events earlier than baseline ({current_date_str} {current_time_str}).
                """

                logger.info("Starting streaming summarization from LLM API...")
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json={
                        "model": self.model_name,
                        "messages": [
                            {"role": "user", "content": summary_prompt}
                        ],
                        "stream": True
                    }
                ) as stream_response:
                    async for line in stream_response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                                token = chunk["choices"][0]["delta"].get("content", "")
                                if token:
                                    full_assistant_reply += token
                                    yield token
                            except Exception:
                                continue
                            
            else:
                direct_res = ""
                if isinstance(parsed, dict):
                    direct_res = (
                        parsed.get("response") or 
                        parsed.get("content") or 
                        parsed.get("message") or 
                        parsed.get("answer") or 
                        parsed.get("text") or 
                        ""
                    )
                
                if not direct_res:
                    direct_res = raw_output

                full_assistant_reply = str(direct_res)
                yield full_assistant_reply

        self.memory.add_record(session_id, "user", user_prompt, category="general")
        self.memory.add_record(session_id, "assistant", full_assistant_reply, category="general")
        logger.info(f"Process stream completed in {time.time() - start_time:.2f}s. Saved history to memory.")