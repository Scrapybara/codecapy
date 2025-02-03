from typing import Literal

from pydantic import BaseModel

from .prompts import (
    ANALYZE_FILES_SYSTEM_PROMPT,
    GENERATE_TESTS_SYSTEM_PROMPT,
    SUMMARIZE_FILE_SYSTEM_PROMPT,
)

# TODO: add Anthropic/Gemini models
GenerateModelType = Literal["o3-mini", "o1", "o1-mini", "gpt-4o", "gpt-4o-mini"]


class GenerateStepConfig(BaseModel):
    model: GenerateModelType
    system_prompt: str


class GenerateConfig(BaseModel):
    analyze_files: GenerateStepConfig = GenerateStepConfig(
        model="o3-mini",
        system_prompt=ANALYZE_FILES_SYSTEM_PROMPT,
    )

    summarize_file: GenerateStepConfig = GenerateStepConfig(
        model="gpt-4o-mini",
        system_prompt=SUMMARIZE_FILE_SYSTEM_PROMPT,
    )

    generate_tests: GenerateStepConfig = GenerateStepConfig(
        model="o3-mini",
        system_prompt=GENERATE_TESTS_SYSTEM_PROMPT,
    )
