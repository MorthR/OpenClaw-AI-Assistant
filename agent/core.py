import json
import requests
import datetime
from skills.registry import SkillRegistry
from agent.memory import MemoryManager

class AgentCore:
    def __init__(self, registry: SkillRegistry, memory: MemoryManager, model_name: str = "qwen2.5:7b", ollama_url: str = "http://localhost:11434/api/generate"):
        self.registry = registry
        self.memory = memory  # Load the memory manager
        self.model_name = model_name
        self.ollama_url = ollama_url

    def process(self, user_prompt: str, session_id: str = "default_user") -> dict:
        now = datetime.datetime.now()
        current_date_str = now.strftime("%Y-%m-%d")
        weekday_str = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][now.weekday()]

        available_skills = self.registry.list_skills()

        history_records = self.memory.get_recent_history(session_id=session_id, limit=6)
        history_text = ""
        if history_records:
            history_text = "[Chat History]:\n" + "\n".join([f"{item['role']}: {item['content']}" for item in history_records]) + "\n\n"

        system_prompt = f"""You are an intelligent personal assistant. Please choose the appropriate tool based on the user's request.

        [Current Time Baseline]:
        - Today's Date is: {current_date_str} ({weekday_str}).
        - When user mentions "today", "tomorrow", or "next week", calculating the exact date based on {current_date_str} is MANDATORY.

        Current available tools: {json.dumps(available_skills, ensure_ascii=False)}

        {history_text}Important Rules:
        1. Focus only on the current user request. DO NOT repeat or mention irrelevant context/emails from chat history unless requested.
        2. If you call email_tool, the parameters must include the "action" field ("search" or "send").
        3. If you call calendar_tool, the parameters must include the "action" field:
        - Add event: action is "add", requires "title", optional "date" (format YYYY-MM-DD, calculated based on today {current_date_str}) and "time".
        - List events: action is "list", optional "date" (format YYYY-MM-DD, defaults to today {current_date_str}).

        When calling tools, you must strictly and only return the following JSON format:
        {{\"tool\": \"tool_name\", \"parameters\": {{\"action\": \"...\", ...}}}}

        When not using any tools, return:
        {{\"tool\": null, \"response\": \"Your direct response\"}}
        """

        # Call Ollama to decide on the tool
        response = requests.post(
            self.ollama_url,
            json={
                "model": self.model_name,
                "prompt": f"{system_prompt}\nCurrent user request: {user_prompt}",
                "stream": False,
                "format": "json"
            }
        )
        
        raw_output = response.json().get("response", "{}")
        try:
            parsed = json.loads(raw_output)
        except Exception:
            parsed = {"tool": None, "response": raw_output}
        
        tool_name = parsed.get("tool")
        if tool_name and (skill := self.registry.get(tool_name)):
            execution_res = skill.run(parsed.get("parameters", {}))
            
            summary_prompt = f"""You are a professional personal AI assistant. Today is {current_date_str} ({weekday_str}).
            Current user request is: "{user_prompt}"
            The system executed the tool 【{tool_name}】 and obtained the following raw data:
            {json.dumps(execution_res, ensure_ascii=False)}

            Instructions:
            1. Please summarize the tool output cleanly and politely in Chinese.
            2. ONLY focus on answering the current request. DO NOT bring up unrelated past topics or emails.
            3. If it is a list of events or emails, format them using clean markdown bullet points.
            """
            summary_response = requests.post(
                self.ollama_url,
                json={
                    "model": self.model_name,
                    "prompt": summary_prompt,
                    "stream": False
                }
            )
            final_text = summary_response.json().get("response", "")
            
            # Save the conversation to memory
            self.memory.add_record(session_id, "user", user_prompt)
            self.memory.add_record(session_id, "assistant", final_text)
            return {"type": "direct_response", "text": final_text}
        
        # Respond directly if no tool is needed
        final_text = parsed.get("response", raw_output)
        self.memory.add_record(session_id, "user", user_prompt)
        self.memory.add_record(session_id, "assistant", final_text)
        return {"type": "direct_response", "text": final_text}