from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class CapyStep(BaseModel):
    type: Literal["bash", "create-env", "instruction", "wait"] = Field(
        description="Type of step to execute"
    )
    command: Optional[str] = None
    text: Optional[str] = None
    seconds: Optional[int] = None


class CapyConfig(BaseModel):
    steps: List[CapyStep]
