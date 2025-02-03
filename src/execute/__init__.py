import time
from typing import List, Optional
import yaml
from github.PullRequest import PullRequest
from scrapybara import Scrapybara
from scrapybara.anthropic import Anthropic
from scrapybara.tools import ComputerTool, BashTool, EditTool
from scrapybara.client import Step, Instance
from ..config import SCRAPYBARA_API_KEY, ANTHROPIC_API_KEY
from ..github import add_pr_comment, edit_pr_comment
from ..generate import GenerateResponse
from ..models import CapyConfig
from .models import TestResult, SetupSchema
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


class ExecuteAgent:
    def __init__(self, config: ExecuteConfig):
        self.config = config
        self.scrapybara_client = Scrapybara(api_key=SCRAPYBARA_API_KEY)
        self.instance: Optional[Instance] = None

    def handle_setup_step(
        self, step: Step, steps: List[Step], pr: PullRequest, comment_id: Optional[int]
    ) -> None:
        """Handle a setup step by updating the steps list and PR comment."""
        steps.append(step)
        if comment_id:
            edit_pr_comment(
                pr,
                comment_id,
                setup_in_progress_comment(steps),
            )

    def handle_test_step(
        self,
        step: Step,
        steps: List[Step],
        pr: PullRequest,
        comment_id: Optional[int],
        test_name: str,
        test_number: int,
    ) -> None:
        """Handle a test step by updating the steps list and PR comment."""
        steps.append(step)
        if comment_id:
            edit_pr_comment(
                pr,
                comment_id,
                test_in_progress_comment(test_number, test_name, steps),
            )

    async def execute_tests(
        self, pr: PullRequest, gr: GenerateResponse, access_token: str
    ):
        """Execute the generated UI tests and report results."""
        setup_comment_id = add_pr_comment(pr, launching_desktop_comment())

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
            self.instance.bash(command=f"git clone {repo_url} {repo_path}")
            self.instance.bash(command=f"cd {repo_path} && git checkout {branch}")

            # Get GitHub variables and set them in the environment
            variables = {}
            try:
                repo_vars = pr.base.repo.get_variables()
                for var in repo_vars:
                    variables[var.name] = var.value
                self.instance.env.set(variables=variables)
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
            except Exception:
                capy_config = None

            # Run setup
            if setup_comment_id:
                edit_pr_comment(
                    pr,
                    setup_comment_id,
                    setup_in_progress_comment([]),
                )

            setup_steps: List[Step] = []

            if not capy_config:
                # Use old setup method with natural language instructions
                setup_response = self.scrapybara_client.act(
                    model=Anthropic(
                        name=self.config.auto_setup.model, api_key=ANTHROPIC_API_KEY
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
                    add_pr_comment(
                        pr,
                        setup_error_comment(setup_response.output.setup_error),
                    )
                    return
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
                                    api_key=ANTHROPIC_API_KEY,
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

                    if not setup_success and setup_comment_id:
                        edit_pr_comment(
                            pr,
                            setup_comment_id,
                            setup_error_with_steps_comment(setup_error, setup_steps),
                        )
                        return

                except Exception as e:
                    if setup_comment_id:
                        edit_pr_comment(
                            pr,
                            setup_comment_id,
                            setup_error_with_steps_comment(str(e), setup_steps),
                        )
                    return

            if setup_comment_id:
                edit_pr_comment(
                    pr,
                    setup_comment_id,
                    setup_complete_comment(setup_steps),
                )

            # Run tests
            test_results = []
            for i, test in enumerate(gr.tests, 1):
                test_comment_id = add_pr_comment(
                    pr,
                    test_starting_comment(i, test.name),
                )
                test_steps: List[Step] = []

                test_response = self.scrapybara_client.act(
                    model=Anthropic(
                        name=self.config.execute_test.model,
                        api_key=ANTHROPIC_API_KEY,
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
                    schema=TestResult,
                    on_step=lambda step: self.handle_test_step(
                        step, test_steps, pr, test_comment_id, test.name, i
                    ),
                )

                if test_comment_id:
                    edit_pr_comment(
                        pr,
                        test_comment_id,
                        test_result_comment(
                            i,
                            test.name,
                            test_response.output.success,
                            test_response.output.error,
                            test_response.output.notes,
                            test_steps,
                        ),
                    )
                test_results.append(test_response.output)

            # Summarize all test results
            passed_tests = sum(1 for r in test_results if r.success)
            total_tests = len(test_results)

            add_pr_comment(
                pr,
                test_summary_comment(passed_tests, total_tests),
            )

        except Exception as e:
            add_pr_comment(
                pr,
                setup_error_comment(str(e)),
            )
        finally:
            if self.instance:
                self.instance.stop()
