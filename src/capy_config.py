from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class CapyStep(BaseModel):
    """capy.yaml step"""

    type: Literal["bash", "create-env", "instruction", "wait"] = Field(
        description="Type of step to execute"
    )
    command: Optional[str] = None
    text: Optional[str] = None
    seconds: Optional[int] = None

    @model_validator(mode="after")
    def validate_step_payload(self) -> "CapyStep":
        """Reject capy.yaml steps that would fail later during setup."""
        if self.type == "bash" and not (self.command and self.command.strip()):
            raise ValueError("bash steps require a non-empty command")

        if self.type == "instruction" and not (self.text and self.text.strip()):
            raise ValueError("instruction steps require non-empty text")

        if self.type == "wait" and self.seconds is not None and self.seconds <= 0:
            raise ValueError("wait steps require seconds to be greater than 0")

        return self


class CapyConfig(BaseModel):
    """capy.yaml config"""

    steps: List[CapyStep]
