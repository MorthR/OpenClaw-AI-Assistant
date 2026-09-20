import json
import datetime
import time
import anyio
import httpx
import inspect
from typing import AsyncGenerator
from skills.registry import SkillRegistry
from agent.memory import MemoryManager
from config.logger import logger

class AgentCore:
    def __init__(self, registry: SkillRegistry, memory: MemoryManager, model_name: str = "qwen2.5:7b", ollama_url: str = "http://localhost:11434/api/generate"):
        self.registry = registry
        self.memory = memory
        self.model_name = model_name
        self.ollama_url = ollama_url

    async def process_stream(self, user_prompt: str, session_id: str = "default_user", user_credentials: dict = None) -> AsyncGenerator[str, None]:
        start_time = time.time()
        logger.info(f"Received user prompt: '{user_prompt}' [Session: {session_id}]")

        GREETINGS = ["hello", "hi", "hey", "who are you", "introduce yourself"]
        normalized_prompt = user_prompt.strip().lower()
        if any(g == normalized_prompt or normalized_prompt.startswith(g) for g in GREETINGS) and len(normalized_prompt) < 20:
            quick_reply = "Hello! I am OpenClaw Assistant, your personal AI agent capable of managing emails and calendars. How can I help you today?"
            logger.info("Fast-pass triggered for greeting message. Skipping LLM decision.")
            self.memory.add_record(session_id, "user", user_prompt, category="general")
            self.memory.add_record(session_id, "assistant", quick_reply, category="general")
            yield quick_reply
            return

        now = datetime.datetime.now()
        current_date_str = now.strftime("%Y-%m-%d")
        weekday_str = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][now.weekday()]

        available_skills = self.registry.list_skills()

        history_records = self.memory.get_recent_history(session_id=session_id, limit=6, category=None)
        history_text = ""
        if history_records:
            history_text = "[Chat History]:\n" + "\n".join([f"{item['role']}: {item['content']}" for item in history_records]) + "\n\n"

        system_prompt = f"""You are an intelligent personal assistant. Analyze the user request and call the correct tool.
        [Current Time Baseline]:
        - Today's Date is: {current_date_str} ({weekday_str}).

        Current available tools: {json.dumps(available_skills, ensure_ascii=False)}

        {history_text}CRITICAL TOOL RULES:
        1. When user asks to SEND/WRITE an email (e.g. "send email", "write email"):
           - You MUST select "email_tool".
           - "action": MUST BE "send".
           - "to_email": Target recipient address.
           - "subject": Email subject.
           - "body": Email body content.

        2. When user asks to READ/SEARCH/QUERY emails (e.g. "query emails", "recent emails"):
           - "action": MUST BE "search".
           - "limit": Integer count.

        EXAMPLES:
        User: "Help me send an email to test@abc.com with the subject 'Notification' and body 'Hello'"
        Output: {{\"tool\": \"email_tool\", \"parameters\": {{\"action\": \"send\", \"to_email\": \"test@abc.com\", \"subject\": \"Notification\", \"body\": \"Hello\"}}}}

        User: "Query the last 5 emails"
        Output: {{\"tool\": \"email_tool\", \"parameters\": {{\"action\": \"search\", \"limit\": 5}}}}

        Return strictly in valid JSON format!
        """
        
        full_assistant_reply = ""
        domain_category = "general"

        async with httpx.AsyncClient(timeout=60.0) as client:
            decision_start = time.time()
            logger.info("Sending request to Ollama for tool decision...")
            
            try:
                decision_response = await client.post(
                    self.ollama_url,
                    json={
                        "model": self.model_name,
                        "prompt": f"{system_prompt}\nCurrent user request: {user_prompt}",
                        "stream": False,
                        "format": "json",
                        "keep_alive": -1
                    }
                )
                logger.info(f"Tool decision step completed in {time.time() - decision_start:.2f}s")
            except Exception as e:
                logger.error(f"Failed to communicate with Ollama: {str(e)}")
                yield "Error: Unable to connect to LLM service."
                return

            raw_output = decision_response.json().get("response", "{}")
            try:
                parsed = json.loads(raw_output)
            except Exception:
                parsed = {"tool": None, "response": raw_output}
            
            tool_name = parsed.get("tool")
            logger.info(f"Decision output parsed. Selected Tool: {tool_name}")

            if tool_name and (skill := self.registry.get(tool_name)):
                tool_start = time.time()
                params = parsed.get("parameters", {})
                logger.info(f"Executing skill [{tool_name}] with params: {params}")
                
                sig = inspect.signature(skill.run)
                if "user_credentials" in sig.parameters:
                    execution_res = await anyio.to_thread.run_sync(skill.run, params, user_credentials)
                else:
                    execution_res = await anyio.to_thread.run_sync(skill.run, params)

                logger.info(f"Skill [{tool_name}] execution finished in {time.time() - tool_start:.2f}s")
                
                summary_prompt = f"""You are a professional personal AI assistant.
                Today's date is {current_date_str} ({weekday_str}).
                User request: "{user_prompt}"
                Tool [{tool_name}] execution result:
                {json.dumps(execution_res, ensure_ascii=False)}

                Instructions:
                1. Inform the user clearly whether the action succeeded or failed based on the tool result.
                2. Do NOT output code fences like ```markdown. Output plain readable text.
                3. Respond politely in Chinese.
                """
                logger.info("Starting streaming summarization from Ollama...")
                async with client.stream(
                    "POST",
                    self.ollama_url,
                    json={
                        "model": self.model_name,
                        "prompt": summary_prompt,
                        "stream": True,
                        "keep_alive": -1
                    }
                ) as stream_response:
                    async for line in stream_response.aiter_lines():
                        if line:
                            chunk = json.loads(line)
                            token = chunk.get("response", "")
                            full_assistant_reply += token
                            yield token

            else:
                direct_res = parsed.get("response", raw_output)
                if direct_res == "Actual direct answer here" or not str(direct_res).strip():
                    direct_res = "I'm sorry, I couldn't process your request. Please try again."
                full_assistant_reply = direct_res
                yield direct_res

        total_time = time.time() - start_time
        logger.info(f"Process stream completed in {total_time:.2f}s. Saving history to memory.")
        self.memory.add_record(session_id, "user", user_prompt, category=domain_category)
        self.memory.add_record(session_id, "assistant", full_assistant_reply)