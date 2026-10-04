import json
import datetime
import time
import httpx
import inspect
import os
import anyio
from typing import AsyncGenerator
from dotenv import load_dotenv
from skills.registry import SkillRegistry
from agent.memory import MemoryManager
from config.logger import logger

load_dotenv()

api_key = os.getenv("LLM_API_KEY", "")
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

    async def process_stream(self, user_prompt: str, session_id: str = "default_user", user_credentials: dict = None) -> AsyncGenerator[str, None]:
        start_time = time.time()
        logger.info(f"Received user prompt: '{user_prompt}' [Session: {session_id}]")

        now = datetime.datetime.now()
        current_date_str = now.strftime("%Y-%m-%d")
        weekday_str = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][now.weekday()]

        available_skills = self.registry.list_skills()

        history_records = self.memory.get_recent_history(session_id=session_id, limit=6, category=None)
        history_text = ""
        if history_records:
            history_text = "[Chat History]:\n" + "\n".join([f"{item['role']}: {item['content']}" for item in history_records]) + "\n\n"

        system_prompt = f"""You are an intelligent personal assistant.
    [Current Time Baseline]:
    - Today's Date is: {current_date_str} ({weekday_str}).

    Available tools:
    {json.dumps(available_skills, ensure_ascii=False, indent=2)}

    {history_text}CRITICAL ROUTING RULES:
    1. If the user asks to check, read, fetch, search, or send emails, you MUST set "tool" to "email_tool".
    2. If a tool is required, fill "tool" with the tool name and provide "parameters". Set "response" to null.
    3. If NO tool is required (general conversation, greeting, self-introduction), set "tool" to null and provide "response".

    EXPECTED OUTPUT FORMAT (JSON):
    For Tool Execution:
    {{"tool": "email_tool", "parameters": {{"action": "search", "limit": 5}}, "response": null}}

    For Direct Chat:
    {{"tool": null, "parameters": null, "response": "Hello! How can I assist you today?"}}
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

            # Execution path 1: Tool invocation
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
                
                summary_prompt = f"""You are a professional personal AI assistant.
                Today's date is {current_date_str} ({weekday_str}).
                User request: "{user_prompt}"
                Tool [{tool_name}] execution result:
                {json.dumps(execution_res, ensure_ascii=False)}

                Instructions:
                1. Summarize the tool result clearly and concisely for the user.
                2. Use clear, plain text in English.
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