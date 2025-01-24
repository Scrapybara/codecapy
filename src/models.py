from typing import List, Optional
from pydantic import BaseModel, Field


class CapyStep(BaseModel):
    type: str = Field(description="Type of step to execute")
    command: Optional[str] = None
    text: Optional[str] = None


class CapyConfig(BaseModel):
    steps: List[CapyStep]
