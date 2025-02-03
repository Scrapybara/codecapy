from typing import Optional, Dict, Any, List
from pydantic import BaseModel


class GitHubWebhookPayload(BaseModel):
    action: Optional[str] = None  # For PR and installation events
    pull_request: Optional[Dict[str, Any]] = None  # For PR events
    ref: Optional[str] = None  # For push events
    repository: Optional[Dict[str, Any]] = None  # Optional for installation events
    repositories: Optional[List[Dict[str, Any]]] = None  # For installation events
    installation: Optional[Dict[str, Any]] = None
    sender: Optional[Dict[str, Any]] = None
    changes: Optional[Dict[str, Any]] = (
        None  # For repository and installation_target events
    )
    target_type: Optional[str] = None  # For installation_target events
