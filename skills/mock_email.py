from .base import BaseSkill

class MockEmailSkill(BaseSkill):
    name = "email_search"
    description = "Search local email inbox by keyword"

    def schema(self) -> dict:
        return {
            "type": "object",
            "properties": {"keyword": {"type": "string"}},
            "required": ["keyword"]
        }

    def run(self, input_data: dict) -> dict:
        keyword = input_data.get("keyword", "")
        return {
            "status": "success",
            "result": [
                {"from": "manager@company.com", "subject": f"Urgent Meeting Notification regarding [{keyword}]", "date": "2026-09-05"}
            ]
        }