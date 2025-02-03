from typing import Callable, Literal

from pydantic import BaseModel

from .prompts import (
    auto_setup_system_prompt,
    execute_test_system_prompt,
    instruction_setup_system_prompt,
)
from src.generate.models import GenerateResponse


# TODO: add more supported models in Act SDK
ExecuteModelType = Literal["claude-3-5-sonnet-20241022"]


class ExecuteStepConfig(BaseModel):
    model: ExecuteModelType
    system_prompt: Callable[[GenerateResponse], str]


class ExecuteConfig(BaseModel):
    auto_setup: ExecuteStepConfig = ExecuteStepConfig(
        model="claude-3-5-sonnet-20241022",
        system_prompt=auto_setup_system_prompt,
    )

    instruction_setup: ExecuteStepConfig = ExecuteStepConfig(
        model="claude-3-5-sonnet-20241022",
        system_prompt=instruction_setup_system_prompt,
    )

    execute_test: ExecuteStepConfig = ExecuteStepConfig(
        model="claude-3-5-sonnet-20241022",
        system_prompt=execute_test_system_prompt,
    )
