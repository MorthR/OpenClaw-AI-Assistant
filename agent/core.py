import json
import requests
from skills.registry import SkillRegistry

class AgentCore:
    def __init__(self, registry: SkillRegistry, model_name: str = "qwen2.5:7b"):
        self.registry = registry
        self.model_name = model_name
        self.ollama_url = "http://localhost:11434/api/generate"

    def process(self, user_prompt: str) -> dict:
        available_skills = self.registry.list_skills()
        
        system_prompt = f"""You are an intelligent personal assistant. Please select the appropriate tool based on the user's request.
        current available tools: {json.dumps(available_skills, ensure_ascii=False)}

        [Important]:
        If calling email_tool, the parameters must include the "action" field, which can be either "search" or "send".
        If searching/reading emails, the action must be "search" and optionally include the "keyword" parameter.
        If sending emails, the action must be "send" and include the "to_email", "subject", and "body" parameters.

        [Usage]:
        When using a tool, you must strictly return the following JSON format:
        {{\"tool\": \"Tool Name\", \"parameters\": {{\"action\": \"search\", \"keyword\": \"Keyword\"}}}}

        When not using any tool, return:
        {{\"tool\": null, \"response\": \"Your direct response\"}}
        """

        response = requests.post(
            self.ollama_url,
            json={
                "model": self.model_name,
                "prompt": f"{system_prompt}\nUser request: {user_prompt}",
                "stream": False,
                "format": "json"
            }
        )
        
        raw_output = response.json().get("response", "{}")
        parsed = json.loads(raw_output)

        tool_name = parsed.get("tool")
        if tool_name and (skill := self.registry.get(tool_name)):
            execution_res = skill.run(parsed.get("parameters", {}))
            
            summary_prompt = f"""User's request is: "{user_prompt}"
            System Execution: The system executed the tool 【{tool_name}】 and obtained the following data:
            {json.dumps(execution_res, ensure_ascii=False)}

            Please format the above data into a clear and readable response in a caring and professional tone.
            If it's an email list, please list a concise and clean list (extracting key senders and subjects), without directly displaying the raw JSON.
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
            return {"type": "direct_response", "text": final_text}
        
        return {"type": "direct_response", "text": parsed.get("response", raw_output)}