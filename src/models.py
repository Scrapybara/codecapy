from typing import List, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict
from scrapybara.client import Step
from .generate.models import TestCase
from .execute.models import TestResult as BaseTestResult
from datetime import datetime


# capy.yaml
class CapyStep(BaseModel):
    """capy.yaml step"""

    type: Literal["bash", "create-env", "instruction", "wait"] = Field(
        description="Type of step to execute"
    )
    command: Optional[str] = None
    text: Optional[str] = None
    seconds: Optional[int] = None


class CapyConfig(BaseModel):
    """capy.yaml config"""

    steps: List[CapyStep]


# Review
class TimestampedStep(Step):
    """Base model for all steps in the review process, extending Scrapybara Step"""

    timestamp: str


class ReviewPhase(BaseModel):
    """Represents a phase of the review process"""

    status: Literal["pending", "in_progress", "complete", "failed"]
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None


class GeneratePhase(ReviewPhase):
    """Generation phase of the review"""

    codebase_summary: str = Field(
        description="A summary of what the repository is for and how it works"
    )
    pr_changes_summary: str = Field(
        description="An overview of the changes made to the codebase in the PR"
    )
    generated_tests: List[TestCase] = Field(
        description="Test cases generated before execution"
    )
    auto_setup_instructions: Optional[str] = Field(
        description="Natural language instructions for setting up the test environment when capy.yaml is not present"
    )
    capy_yaml_content: Optional[str] = Field(
        description="Content of the capy.yaml file if it exists"
    )


class SetupPhase(ReviewPhase):
    """Setup phase of the review"""

    steps: List[TimestampedStep]


class TestResult(BaseTestResult):
    """Extended test result that includes execution steps"""

    test_number: int = Field(description="The sequential number of the test")
    test_name: str = Field(description="Name of the test that was executed")
    steps: List[TimestampedStep] = Field(
        description="Steps taken during test execution"
    )


class ExecutePhase(ReviewPhase):
    """Test execution phase of the review"""

    test_results: List[TestResult] = Field(description="Results of all test executions")


class Review(BaseModel):
    """DB Review model"""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[str]
    repo_id: int
    pr_number: int
    commit_sha: str
    started_at: str
    completed_at: Optional[str] = None
    status: Literal["pending", "in_progress", "complete", "failed"] = "pending"
    total_tests: Optional[int] = None
    passed_tests: Optional[int] = None
    generate: GeneratePhase
    setup: SetupPhase
    execute: ExecutePhase

    @classmethod
    def create_pending(
        cls, repo_id: int, pr_number: int, commit_sha: str, current_time: str
    ) -> "Review":
        """Create a new pending review with generate phase in progress"""
        generate_phase = GeneratePhase(
            status="in_progress",
            started_at=current_time,
            codebase_summary="",
            pr_changes_summary="",
            generated_tests=[],
            auto_setup_instructions=None,
            capy_yaml_content=None,
        )

        setup_phase = SetupPhase(
            status="pending",
            steps=[],
        )

        execute_phase = ExecutePhase(
            status="pending",
            test_results=[],
        )

        return cls(
            id=None,  # Will be set after DB insert
            repo_id=repo_id,
            pr_number=pr_number,
            commit_sha=commit_sha,
            started_at=current_time,
            status="in_progress",
            generate=generate_phase,
            setup=setup_phase,
            execute=execute_phase,
        )


# Repo
class Repo(BaseModel):
    """DB Repo model"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_github_id: int
    installation_id: int
    name: str
    owner: str
    owner_avatar_url: str
    url: str
    is_private: bool
    connected: bool
    updated_at: str

    @classmethod
    def from_github_data(
        cls, repo_data: dict, installation_id: int, connected: Optional[bool] = None
    ) -> "Repo":
        """Create a Repo instance from GitHub API data"""
        return cls(
            id=repo_data["id"],
            owner_github_id=repo_data["owner"]["id"],
            installation_id=installation_id,
            name=repo_data["name"],
            owner=repo_data["owner"]["login"],
            owner_avatar_url=repo_data["owner"]["avatar_url"],
            url=repo_data["html_url"],
            is_private=repo_data["private"],
            connected=connected if connected is not None else True,
            updated_at=datetime.now().isoformat(),
        )
