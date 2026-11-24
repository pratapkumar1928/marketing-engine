from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Slot:
    app: str
    slot_id: str  # "YYYY-MM-DD#i"
    at: datetime
    platforms: list[str]


@dataclass
class Plan:
    slot: Slot
    recipe_id: str
    content_id: str
    combo: str


@dataclass
class Copy:
    hook: str
    texts: dict[str, str] = field(default_factory=dict)
    caption: str = ""
    hashtags: list[str] = field(default_factory=list)


@dataclass
class Published:
    platform: str
    post_id: str
    url: str


class PublishError(Exception):
    def __init__(self, msg: str, retryable: bool):
        super().__init__(msg)
        self.retryable = retryable


class CopyRejected(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason
