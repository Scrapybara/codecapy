import time
from typing import List, Optional
import yaml
from github.PullRequest import PullRequest
from scrapybara import Scrapybara
from scrapybara.anthropic import Anthropic
from scrapybara.tools import ComputerTool, BashTool, EditTool
from scrapybara.client import Step
from ..config import SCRAPYBARA_API_KEY
from ..github import add_pr_comment, edit_pr_comment
from ..generate import GenerateResponse
from ..models import CapyConfig
from .models import TestResult, SetupSchema
from .prompts import (
    get_auto_setup_system_prompt,
    get_instruction_setup_system_prompt,
    get_test_system_prompt,
)


def format_agent_steps(steps: List[Step]) -> str:
    """Format agent steps as code blocks and trim messages to 50 characters."""
    formatted_steps = []

    for step in steps:
        # Format tool calls
        tool_call_lines = []
        if step.tool_calls:
            for call in step.tool_calls:
                # Redact editor tool calls
                args = (
                    "[REDACTED]"
                    if call.tool_name == "str_replace_editor"
                    else call.args
                )
                tool_call_lines.append(f"{call.tool_name}: {args}")

        # Get step text if it exists
        step_text = ""
        if step.text and step.text.strip():
            # Get the step text without leading dash/bullet
            step_text = step.text.lstrip("- ")
            # Split on first period to remove any numbering
            step_text = step_text.split(". ", 1)[-1]

        # Only add step if there's text or tool calls
        if step_text or tool_call_lines:
            # Combine into code block with text only if it exists
            formatted_step = f"```\n{step_text + chr(10) if step_text else ''}{chr(10).join(tool_call_lines)}\n```"
            formatted_steps.append(formatted_step)

    return "\n".join(formatted_steps)


def handle_setup_step(
    step: Step, steps: List[Step], pr: PullRequest, comment_id: Optional[int]
) -> None:
    """Handle a setup step by updating the steps list and PR comment."""
    steps.append(step)
    if comment_id:
        edit_pr_comment(
            pr,
            comment_id,
            f"""🔧 Setting up test environment...

<details>
<summary>Agent Steps</summary>

{format_agent_steps(steps)}
</details>""",
        )


def handle_test_step(
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
            f"""🧪 Running test {test_number}: {test_name}...

<details>
<summary>Agent Steps</summary>

{format_agent_steps(steps)}
</details>""",
        )


async def execute_tests(pr: PullRequest, gr: GenerateResponse, access_token: str):
    """Execute the generated UI tests and report results."""
    setup_comment_id = add_pr_comment(pr, "🚀 Launching Scrapybara desktop...")

    scrapybara_client = Scrapybara(api_key=SCRAPYBARA_API_KEY)
    instance = None

    try:
        instance = scrapybara_client.start(instance_type="large")

        # Get repo details and access token
        repo_name = pr.base.repo.full_name
        repo_url = f"https://x-access-token:{access_token}@github.com/{repo_name}.git"
        branch = pr.head.ref

        # Clone the repository
        repo_path = f"/home/scrapybara/Documents/{repo_name}"
        instance.bash(command=f"git clone {repo_url} {repo_path}")
        instance.bash(command=f"cd {repo_path} && git checkout {branch}")

        # Get GitHub variables and set them in the environment
        variables = {}
        try:
            repo_vars = pr.base.repo.get_variables()
            for var in repo_vars:
                variables[var.name] = var.value
            instance.env.set(variables=variables)
        except Exception as e:
            if setup_comment_id:
                edit_pr_comment(
                    pr,
                    setup_comment_id,
                    f"""🚀 Launching Scrapybara desktop...

⚠️ Error fetching GitHub variables, continuing setup: 
```
{str(e)}
```""",
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
                """🔧 Setting up test environment...

<details>
<summary>Agent Steps</summary>

</details>""",
            )

        setup_steps: List[Step] = []

        if not capy_config:
            # Use old setup method with natural language instructions
            setup_response = scrapybara_client.act(
                model=Anthropic(),
                tools=[
                    BashTool(instance),
                    ComputerTool(instance),
                    EditTool(instance),
                ],
                system=get_auto_setup_system_prompt(gr),
                prompt=f"""Here are the setup instructions:

{gr.setup_instructions}

Available variables that have been set in the environment:
{chr(10).join(f'- {key}: {variables[key]}' for key in variables.keys())}

Please follow these instructions to set up the test environment in {repo_path}. The variables are already available in the environment, but you may need to create a .env file if the application requires it.""",
                schema=SetupSchema,
                on_step=lambda step: handle_setup_step(
                    step, setup_steps, pr, setup_comment_id
                ),
            )

            if not setup_response.output.setup_success:
                add_pr_comment(
                    pr,
                    f"""❌ Error setting up test environment: 
```
{setup_response.output.setup_error}
```""",
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
                        instance.bash(command=command)

                        # Add step to comment
                        handle_setup_step(
                            Step(text=f"Running command: {command}"),
                            setup_steps,
                            pr,
                            setup_comment_id,
                        )

                    elif step.type == "create-env":
                        env_content = "\n".join(
                            f"{key}={value}" for key, value in variables.items()
                        )
                        instance.file.write(
                            path=f"{repo_path}/.env", content=env_content
                        )

                        # Add step to comment
                        handle_setup_step(
                            Step(
                                text=f"Creating .env file with {len(variables)} variables"
                            ),
                            setup_steps,
                            pr,
                            setup_comment_id,
                        )

                    elif step.type == "instruction":
                        instruction_response = scrapybara_client.act(
                            model=Anthropic(),
                            tools=[
                                BashTool(instance),
                                ComputerTool(instance),
                                EditTool(instance),
                            ],
                            system=get_instruction_setup_system_prompt(gr),
                            prompt=step.text,
                            schema=SetupSchema,
                            on_step=lambda step: handle_setup_step(
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
                        handle_setup_step(
                            Step(text=f"Waiting {step.seconds or 10} seconds"),
                            setup_steps,
                            pr,
                            setup_comment_id,
                        )

                if not setup_success and setup_comment_id:
                    edit_pr_comment(
                        pr,
                        setup_comment_id,
                        f"""❌ Error setting up test environment: 
```
{setup_error}
```

<details>
<summary>Agent Steps</summary>

{format_agent_steps(setup_steps)}
</details>""",
                    )
                    return

            except Exception as e:
                if setup_comment_id:
                    edit_pr_comment(
                        pr,
                        setup_comment_id,
                        f"""❌ Error setting up test environment: 
```
{str(e)}
```

<details>
<summary>Agent Steps</summary>

{format_agent_steps(setup_steps)}
</details>""",
                    )
                return

        if setup_comment_id:
            edit_pr_comment(
                pr,
                setup_comment_id,
                f"""✅ Setup complete! Running tests...

<details>
<summary>Agent Steps</summary>

{format_agent_steps(setup_steps)}
</details>""",
            )

        # Run tests
        test_results = []
        for i, test in enumerate(gr.tests, 1):
            test_comment_id = add_pr_comment(pr, f"🧪 Running test {i}: {test.name}...")
            test_steps: List[Step] = []

            test_response = scrapybara_client.act(
                model=Anthropic(),
                tools=[
                    BashTool(instance),
                    ComputerTool(instance),
                    EditTool(instance),
                ],
                system=get_test_system_prompt(gr),
                prompt=f"""Please execute the following test:

Test Name: {test.name}
Description: {test.description}

Prerequisites:
{chr(10).join(f'- {prereq}' for prereq in test.prerequisites)}

Steps to Execute:
{chr(10).join(f'{i+1}. {step}' for i, step in enumerate(test.steps))}

Expected Result:
{test.expected_result}

Priority: {test.priority}

Please follow these steps exactly, take screenshots at key moments, and verify the results carefully.""",
                schema=TestResult,
                on_step=lambda step: handle_test_step(
                    step, test_steps, pr, test_comment_id, test.name, i
                ),
            )

            # Format the result comment with screenshots and steps
            if test_response.output.success:
                result_comment = f"""✅ Test {i} Passed: {test.name}

{test_response.output.notes if test_response.output.notes else ""}

<details>
<summary>Agent Steps</summary>

{format_agent_steps(test_steps)}
</details>"""
            else:
                result_comment = f"""❌ Test {i} Failed: {test.name}

Error: {test_response.output.error}
{test_response.output.notes if test_response.output.notes else ""}

<details>
<summary>Agent Steps</summary>

{format_agent_steps(test_steps)}
</details>"""

            if test_comment_id:
                edit_pr_comment(pr, test_comment_id, result_comment)
            test_results.append(test_response.output)

        # Summarize all test results
        passed_tests = sum(1 for r in test_results if r.success)
        total_tests = len(test_results)

        summary = f"""# CodeCapy Test Results 📊

{passed_tests}/{total_tests} tests passed

{'🎉 All tests passed!' if passed_tests == total_tests else '⚠️ Some tests failed. Please check the individual test results above for details.'}"""

        add_pr_comment(pr, summary)

    except Exception as e:
        add_pr_comment(
            pr,
            f"""❌ Error during test execution: 
```
{str(e)}
```""",
        )
    finally:
        if instance:
            instance.stop()
