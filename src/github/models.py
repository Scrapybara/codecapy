from typing import Optional, Dict, Any, List
from pydantic import BaseModel


class GitHubWebhookPayload(BaseModel):
    action: Optional[str] = None
    pull_request: Optional[Dict[str, Any]] = None
    ref: Optional[str] = None
    repository: Optional[Dict[str, Any]] = None
    installation: Optional[Dict[str, Any]] = None
