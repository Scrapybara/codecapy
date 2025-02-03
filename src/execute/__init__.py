import time
from typing import List, Optional
import yaml
from github.PullRequest import PullRequest
from scrapybara import Scrapybara
from scrapybara.anthropic import Anthropic
from scrapybara.tools import ComputerTool, BashTool, EditTool
from scrapybara.client import Step, Instance
from ..config import settings
from ..github import add_pr_comment, edit_pr_comment
from ..generate import GenerateResponse
from ..models import CapyConfig, TestResult
from .models import TestResult as BaseTestResult, SetupSchema
from .config import ExecuteConfig
from .prompts import (
    auto_setup_user_prompt,
    execute_test_user_prompt,
)
from .comments import (
    setup_in_progress_comment,
    setup_error_comment,
    setup_error_with_steps_comment,
    setup_complete_comment,
    test_starting_comment,
    test_result_comment,
    test_summary_comment,
    test_in_progress_comment,
    launching_desktop_comment,
    launching_desktop_error_comment,
)
from datetime import datetime
from ..models import Review, TimestampedStep
from ..database import upsert_review


class ExecuteAgent:
    def __init__(self, config: ExecuteConfig):
        self.config = config
        self.scrapybara_client = Scrapybara(api_key=settings.scrapybara_api_key)
        self.instance: Optional[Instance] = None
        self._review: Optional[Review] = None

    def handle_setup_step(
        self,
        step: Step,
        steps: List[TimestampedStep],
        pr: PullRequest,
        comment_id: Optional[int],
    ) -> None:
        """Handle a setup step by updating the steps list and PR comment."""
        timestamped_step = TimestampedStep(
            **step.model_dump(),
            timestamp=datetime.now().isoformat(),
        )
        steps.append(timestamped_step)

        # Update review if we have one
        if self._review:
            self._review.setup.steps = [
                s for s in steps if isinstance(s, TimestampedStep)
            ]
            self._review = upsert_review(self._review)

        if comment_id:
            edit_pr_comment(
                pr,
                comment_id,
                setup_in_progress_comment(steps),
            )

    def handle_test_step(
        self,
        step: Step,
        steps: List[TimestampedStep],
        pr: PullRequest,
        comment_id: Optional[int],
        test_name: str,
        test_number: int,
    ) -> None:
        """Handle a test step by updating the steps list and PR comment."""
        timestamped_step = TimestampedStep(
            **step.model_dump(),
            timestamp=datetime.now().isoformat(),
        )
        steps.append(timestamped_step)

        # Update review if we have one
        if self._review:
            # Find or create the test result for this test
            test_result = None
            for result in self._review.execute.test_results:
                if result.test_number == test_number and result.test_name == test_name:
                    test_result = result
                    break

            if not test_result:
                # Create a new test result if it doesn't exist
                test_result = TestResult(
                    test_number=test_number,
                    test_name=test_name,
                    steps=[],
                    success=False,
                    error=None,
                    notes=None,
                )
                self._review.execute.test_results.append(test_result)

            # Update the steps for this test result
            test_result.steps = steps
            self._review = upsert_review(self._review)

        if comment_id:
            edit_pr_comment(
                pr,
                comment_id,
                test_in_progress_comment(test_number, test_name, steps),
            )

    async def execute_tests(
        self,
        pr: PullRequest,
        gr: GenerateResponse,
        access_token: str,
        review: Optional[Review] = None,
    ) -> bool:
        """Execute the generated UI tests and report results."""
        setup_comment_id = add_pr_comment(pr, launching_desktop_comment())
        self._review = review

        # Start setup phase immediately
        if review:
            review.setup.status = "in_progress"
            review.setup.started_at = datetime.now().isoformat()
            review = upsert_review(review)

        try:
            self.instance = self.scrapybara_client.start(instance_type="large")

            # Get repo details and access token
            repo_name = pr.base.repo.full_name
            repo_url = (
                f"https://x-access-token:{access_token}@github.com/{repo_name}.git"
            )
            branch = pr.head.ref

            # Clone the repository
            repo_path = f"/home/scrapybara/Documents/{repo_name}"
            current_step = TimestampedStep(
                text=f"Cloning repository {repo_name}...",
                timestamp=datetime.now().isoformat(),
            )
            setup_steps: List[TimestampedStep] = [current_step]
            if review:
                review.setup.steps = setup_steps
                review = upsert_review(review)

            self.instance.bash(command=f"git clone {repo_url} {repo_path}")
            self.instance.bash(command=f"cd {repo_path} && git checkout {branch}")

            # Get GitHub variables and set them in the environment
            variables = {}
            try:
                repo_vars = pr.base.repo.get_variables()
                for var in repo_vars:
                    variables[var.name] = var.value
                self.instance.env.set(variables=variables)

                current_step = TimestampedStep(
                    text=f"Setting up {len(variables)} environment variables...",
                    timestamp=datetime.now().isoformat(),
                )
                setup_steps.append(current_step)
                if review:
                    review.setup.steps = setup_steps
                    review = upsert_review(review)

            except Exception as e:
                if setup_comment_id:
                    edit_pr_comment(
                        pr,
                        setup_comment_id,
                        launching_desktop_error_comment(str(e)),
                    )

            # Get capy.yaml content
            try:
                content = pr.base.repo.get_contents("capy.yaml", ref=pr.head.ref)
                if isinstance(content, list):
                    raise ValueError("capy.yaml should not be a directory")
                capy_content = content.decoded_content.decode()
                capy_config = CapyConfig.model_validate(yaml.safe_load(capy_content))

                current_step = TimestampedStep(
                    text="Found capy.yaml configuration",
                    timestamp=datetime.now().isoformat(),
                )
                setup_steps.append(current_step)
                if review:
                    review.setup.steps = setup_steps
                    review = upsert_review(review)

            except Exception:
                capy_config = None

            # Run setup
            if setup_comment_id:
                edit_pr_comment(
                    pr,
                    setup_comment_id,
                    setup_in_progress_comment([]),
                )

            if not capy_config:
                # Use old setup method with natural language instructions
                setup_response = self.scrapybara_client.act(
                    model=Anthropic(
                        name=self.config.auto_setup.model,
                        api_key=settings.anthropic_api_key,
                    ),
                    tools=[
                        BashTool(self.instance),
                        ComputerTool(self.instance),
                        EditTool(self.instance),
                    ],
                    system=self.config.auto_setup.system_prompt(gr),
                    prompt=auto_setup_user_prompt(
                        gr.setup_instructions
                        or "Set up the repository to the best of your ability",
                        variables,
                        repo_path,
                    ),
                    schema=SetupSchema,
                    on_step=lambda step: self.handle_setup_step(
                        step, setup_steps, pr, setup_comment_id
                    ),
                )

                if not setup_response.output.setup_success:
                    if review:
                        review.setup.status = "failed"
                        review.setup.error = setup_response.output.setup_error
                        review.status = "failed"
                        review = upsert_review(review)
                    add_pr_comment(
                        pr,
                        setup_error_comment(setup_response.output.setup_error),
                    )
                    return False
            else:
                # Use new setup method with capy.yaml
                setup_success = True
                setup_error = None

                try:
                    for step in capy_config.steps:
                        if step.type == "bash":
                            # Replace {{repo_dir}} with actual repo path
                            if not step.command:
                                setup_success = False
                                setup_error = "Bash step missing command"
                                break

                            command = step.command.replace("{{repo_dir}}", repo_path)
                            self.instance.bash(command=command)

                            # Add step to comment
                            self.handle_setup_step(
                                Step(text=f"Running command: {command}"),
                                setup_steps,
                                pr,
                                setup_comment_id,
                            )

                        elif step.type == "create-env":
                            env_content = "\n".join(
                                f"{key}={value}" for key, value in variables.items()
                            )
                            self.instance.file.write(
                                path=f"{repo_path}/.env", content=env_content
                            )

                            # Add step to comment
                            self.handle_setup_step(
                                Step(
                                    text=f"Creating .env file with {len(variables)} variables"
                                ),
                                setup_steps,
                                pr,
                                setup_comment_id,
                            )

                        elif step.type == "instruction":
                            instruction_response = self.scrapybara_client.act(
                                model=Anthropic(
                                    name=self.config.instruction_setup.model,
                                    api_key=settings.anthropic_api_key,
                                ),
                                tools=[
                                    BashTool(self.instance),
                                    ComputerTool(self.instance),
                                    EditTool(self.instance),
                                ],
                                system=self.config.instruction_setup.system_prompt(gr),
                                prompt=step.text,
                                schema=SetupSchema,
                                on_step=lambda step: self.handle_setup_step(
                                    step, setup_steps, pr, setup_comment_id
                                ),
                            )
                            if not instruction_response.output.setup_success:
                                setup_success = False
                                setup_error = instruction_response.output.setup_error
                                break

                        elif step.type == "wait":
                            if step.seconds:
                                time.sleep(step.seconds)
                            else:
                                time.sleep(10)

                            # Add step to comment
                            self.handle_setup_step(
                                Step(text=f"Waiting {step.seconds or 10} seconds"),
                                setup_steps,
                                pr,
                                setup_comment_id,
                            )

                    if not setup_success:
                        if review:
                            review.setup.status = "failed"
                            review.setup.error = setup_error
                            review.status = "failed"
                            review = upsert_review(review)
                        if setup_comment_id:
                            edit_pr_comment(
                                pr,
                                setup_comment_id,
                                setup_error_with_steps_comment(
                                    setup_error, setup_steps
                                ),
                            )
                        return False

                except Exception as e:
                    if review:
                        review.setup.status = "failed"
                        review.setup.error = str(e)
                        review.status = "failed"
                        review = upsert_review(review)
                    if setup_comment_id:
                        edit_pr_comment(
                            pr,
                            setup_comment_id,
                            setup_error_with_steps_comment(str(e), setup_steps),
                        )
                    return False

            # Setup complete
            if review:
                review.setup.steps = setup_steps
                review.setup.status = "complete"
                review.setup.completed_at = datetime.now().isoformat()
                review = upsert_review(review)

            if setup_comment_id:
                edit_pr_comment(
                    pr,
                    setup_comment_id,
                    setup_complete_comment(setup_steps),
                )

            # Start execute phase if we have a review
            if review:
                review.execute.status = "in_progress"
                review.execute.started_at = datetime.now().isoformat()
                review = upsert_review(review)

            # Run tests
            test_results: List[TestResult] = []
            for i, test in enumerate(gr.tests, 1):
                test_comment_id = add_pr_comment(
                    pr,
                    test_starting_comment(i, test.name),
                )
                test_steps: List[TimestampedStep] = []

                test_response = self.scrapybara_client.act(
                    model=Anthropic(
                        name=self.config.execute_test.model,
                        api_key=settings.anthropic_api_key,
                    ),
                    tools=[
                        BashTool(self.instance),
                        ComputerTool(self.instance),
                        EditTool(self.instance),
                    ],
                    system=self.config.execute_test.system_prompt(gr),
                    prompt=execute_test_user_prompt(
                        test.name,
                        test.description,
                        test.prerequisites,
                        test.steps,
                        test.expected_result,
                        test.priority,
                    ),
                    schema=BaseTestResult,
                    on_step=lambda step: self.handle_test_step(
                        step, test_steps, pr, test_comment_id, test.name, i
                    ),
                )

                # Get the test result that was created during step handling
                test_result = None
                if review:
                    for result in review.execute.test_results:
                        if result.test_number == i and result.test_name == test.name:
                            test_result = result
                            break

                # If no test result exists (no review), create a new one
                if not test_result:
                    test_result = TestResult(
                        test_number=i,
                        test_name=test.name,
                        steps=test_steps,
                        success=test_response.output.success,
                        error=test_response.output.error,
                        notes=test_response.output.notes,
                    )
                    test_results.append(test_result)
                else:
                    # Update existing test result with final status
                    test_result.success = test_response.output.success
                    test_result.error = test_response.output.error
                    test_result.notes = test_response.output.notes
                    if test_result not in test_results:
                        test_results.append(test_result)

                # Update review after each test if we have one
                if review:
                    # Check if we have a new passed test
                    if test_result.success:
                        review.passed_tests = (review.passed_tests or 0) + 1
                    review.total_tests = len(test_results)
                    review = upsert_review(review)

                if test_comment_id:
                    edit_pr_comment(
                        pr,
                        test_comment_id,
                        test_result_comment(
                            test_result.test_number,
                            test_result.test_name,
                            test_result.success,
                            test_result.error,
                            test_result.notes,
                            test_result.steps,
                        ),
                    )

            # Summarize all test results
            passed_tests = sum(1 for r in test_results if r.success)
            total_tests = len(test_results)

            # Update review with test results if we have one
            if review:
                review.total_tests = total_tests
                review.passed_tests = passed_tests
                review.execute.test_results = test_results
                review.execute.status = "complete"
                review.execute.completed_at = datetime.now().isoformat()
                review.status = "complete"
                review.completed_at = datetime.now().isoformat()
                review = upsert_review(review)

            add_pr_comment(
                pr,
                test_summary_comment(passed_tests, total_tests),
            )

            return True

        except Exception as e:
            if review:
                review.status = "failed"
                if review.setup.status == "in_progress":
                    review.setup.status = "failed"
                    review.setup.error = str(e)
                elif review.execute.status == "in_progress":
                    review.execute.status = "failed"
                    review.execute.error = str(e)
                review = upsert_review(review)
            add_pr_comment(
                pr,
                setup_error_comment(str(e)),
            )
            return False
        finally:
            if self.instance:
                self.instance.stop()
