from typing import Optional, Dict, Any
from pydantic import BaseModel


class GitHubWebhookPayload(BaseModel):
    action: Optional[str] = None  # For PR events
    pull_request: Optional[Dict[str, Any]] = None  # For PR events
    ref: Optional[str] = None  # For push events
    repository: Dict[str, Any]
    installation: Optional[Dict[str, Any]] = None

    @property
    def is_pull_request(self) -> bool:
        return self.action is not None and self.pull_request is not None
