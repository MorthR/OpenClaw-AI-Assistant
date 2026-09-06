from abc import ABC, abstractmethod

class BaseSkill(ABC):
    name: str
    description: str

    @abstractmethod
    def schema(self) -> dict:
        pass

    @abstractmethod
    def run(self, input_data: dict) -> dict:
        pass