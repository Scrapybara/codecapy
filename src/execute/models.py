from typing import Literal, Optional
from pydantic import BaseModel, Field


class TestResult(BaseModel):
    success: bool = Field(description="Whether the test passed or failed")
    error: Optional[str] = Field(description="Error message if the test failed")
    notes: Optional[str] = Field(
        description="Any additional observations or notes about the test execution"
    )


class SetupSchema(BaseModel):
    setup_success: bool = Field(description="Whether the setup was successful")
    setup_error: Optional[str] = Field(description="Error message if the setup failed")
