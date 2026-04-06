from dataclasses import dataclass, field
from typing import Optional

MAX_HISTORY = 20  # keep last N messages in context


@dataclass
class Message:
    agent_id: str
    agent_name: str
    role: str
    specialty: str
    content: str
    round: int


class SharedContext:
    def __init__(self):
        self.topic: str = ""
        self.history: list[Message] = []

    def reset(self, topic: str = ""):
        self.topic = topic
        self.history = []

    def add_message(self, msg: Message):
        self.history.append(msg)
        # Trim to last MAX_HISTORY entries
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]

    def snapshot(self) -> dict:
        """Return a plain-dict snapshot safe to pass into agent builders."""
        return {
            "topic": self.topic,
            "history": [
                {
                    "agent_id": m.agent_id,
                    "agent_name": m.agent_name,
                    "role": m.role,
                    "specialty": m.specialty,
                    "content": m.content,
                    "round": m.round,
                }
                for m in self.history
            ],
        }
