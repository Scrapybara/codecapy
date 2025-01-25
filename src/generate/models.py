from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class TestCase(BaseModel):
    name: str = Field(
        description="A clear, descriptive name for the test that indicates what user action or feature is being tested"
    )
    description: str = Field(
        description="A friendly explanation of what this test is checking and why it's important"
    )
    prerequisites: List[str] = Field(
        description="List of things needed before starting the test (like 'Being logged in' or 'Having items in cart')"
    )
    steps: List[str] = Field(
        description="Step-by-step instructions that anyone can follow to test the feature (like 'Click the blue Submit button')"
    )
    expected_result: str = Field(
        description="A clear description of what should happen when the test is done correctly"
    )
    priority: Literal["high", "medium", "low"] = Field(
        description="How important this test is"
    )


class GenerateResponse(BaseModel):
    summary: str = Field(description="A summary of the changes made to the codebase")
    tests: List[TestCase] = Field(description="The list of test cases to run")
    setup_instructions: Optional[str] = Field(
        description="Instructions for setting up the test environment. Only provided when capy.yaml is not present."
    )


class ImportantFile(BaseModel):
    path: str = Field(description="The path to the file")
    reason: str = Field(description="The reason the file is important")


class FileAnalysisResponse(BaseModel):
    files: List[ImportantFile]
