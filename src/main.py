from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.security import HTTPBearer
from github import Github, GithubIntegration
from github.PullRequest import PullRequest
from scrapybara import Scrapybara
from scrapybara.anthropic import Anthropic
from scrapybara.tools import ComputerTool, BashTool, EditTool
from pydantic import BaseModel
from typing import List, Optional
import hmac
import hashlib
import os
from dotenv import load_dotenv
from pydantic import BaseModel
from openai import OpenAI
from .prompts import (
    TestCase,
    TestResult,
    GenerateResponse,
    GENERATE_SYSTEM_PROMPT,
    SETUP_SYSTEM_PROMPT,
    TEST_SYSTEM_PROMPT,
    generate_test_prompt,
)

load_dotenv()

# Initialize FastAPI app
app = FastAPI()
security = HTTPBearer()

GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")
GITHUB_APP_ID = os.getenv("GITHUB_APP_ID")
GITHUB_PRIVATE_KEY_PATH = os.getenv("GITHUB_PRIVATE_KEY_PATH")
SCRAPYBARA_API_KEY = os.getenv("SCRAPYBARA_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


def get_github_private_key():
    """Get GitHub private key from file."""
    if not GITHUB_PRIVATE_KEY_PATH or not os.path.exists(GITHUB_PRIVATE_KEY_PATH):
        raise ValueError("GitHub private key file not found at specified path")
    with open(GITHUB_PRIVATE_KEY_PATH, "r") as f:
        return f.read().strip()


def get_github_integration():
    """Create GitHub Integration instance."""
    return GithubIntegration(
        integration_id=GITHUB_APP_ID,
        private_key=get_github_private_key(),
    )


def get_installation_access_token(installation_id: int) -> str:
    """Get an access token for a GitHub App installation."""
    integration = get_github_integration()
    access_token = integration.get_access_token(installation_id)
    return access_token.token


def add_pr_comment(pr: PullRequest, comment: str):
    """Add a comment to a pull request."""
    try:
        pr.create_issue_comment(comment)
    except Exception as e:
        print(f"Error adding comment to PR: {e}")


class GitHubWebhookPayload(BaseModel):
    action: str
    pull_request: dict
    repository: dict
    installation: Optional[dict]


def verify_github_webhook(request: Request, payload: bytes = None):
    if not GITHUB_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=500, detail="GitHub webhook secret not configured"
        )

    signature = request.headers.get("X-Hub-Signature-256")
    if not signature:
        raise HTTPException(status_code=400, detail="No signature header found")

    hash_object = hmac.new(
        GITHUB_WEBHOOK_SECRET.encode("utf-8"), msg=payload, digestmod=hashlib.sha256
    )
    expected_signature = f"sha256={hash_object.hexdigest()}"

    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")


async def generate_tests(pr: PullRequest) -> Optional[GenerateResponse]:
    """Process PR changes and run tests using Scrapybara."""
    # Add initial comment that we're processing the PR
    add_pr_comment(pr, "🔍 Analyzing PR changes and preparing to run tests...")

    # Initialize OpenAI client
    openai_client = OpenAI(api_key=OPENAI_API_KEY)

    try:
        # Get PR details
        pr_title = pr.title
        pr_description = pr.body or ""

        # Get file changes
        file_changes = []
        for file in pr.get_files():
            if file.patch:
                file_changes.append(f"File: {file.filename}\nChanges:\n{file.patch}\n")
        file_changes_str = "\n".join(file_changes)

        # Get repository context
        repo = pr.base.repo

        # Get README content
        readme_content = repo.get_contents("README.md").decoded_content.decode()

        # Get file tree (excluding common directories to avoid noise)
        def get_tree_content(repo, path="", level=0, max_level=3):
            try:
                contents = repo.get_contents(path)
                if not isinstance(contents, list):
                    contents = [contents]

                tree = []
                for content in contents:
                    if content.type == "dir":
                        if level < max_level and not any(
                            content.path.startswith(x)
                            for x in [".git", "node_modules", "__pycache__", ".venv"]
                        ):
                            subtree = get_tree_content(
                                repo, content.path, level + 1, max_level
                            )
                            if subtree:
                                tree.append(
                                    f"{'  ' * level}📁 {content.name}/\n" + subtree
                                )
                    else:
                        if not content.name.startswith(
                            "."
                        ) and not content.name.endswith((".pyc", ".pyo")):
                            tree.append(f"{'  ' * level}📄 {content.name}")
                return "\n".join(tree)
            except Exception as e:
                return f"Error getting tree for {path}: {str(e)}"

        file_tree = get_tree_content(repo)

        # Generate the test prompt with enhanced context
        test_prompt = generate_test_prompt(
            pr_title=pr_title,
            pr_description=pr_description,
            file_changes=file_changes_str,
            readme_content=readme_content,
            file_tree=file_tree,
        )

        print(test_prompt)

        # Generate test cases
        completion = openai_client.beta.chat.completions.parse(
            model="o1-2024-12-17",
            messages=[
                {"role": "system", "content": GENERATE_SYSTEM_PROMPT},
                {"role": "user", "content": test_prompt},
            ],
            response_format=GenerateResponse,
        )

        # Parse the test cases
        generate_response = GenerateResponse.model_validate(
            completion.choices[0].message.parsed
        )

        # Format test results for the comment
        test_details = []
        for i, test in enumerate(generate_response.tests, 1):
            test_details.append(
                f"""
### {i}: {test.name} {'❗️' if test.priority == 'low' else '❗️❗️' if test.priority == 'medium' else '❗️❗️❗️'}

**Description**: {test.description}

**Prerequisites**:
{chr(10).join(f'- {prereq}' for prereq in test.prerequisites)}

**Steps**:
{chr(10).join(f'{i+1}. {step}' for i, step in enumerate(test.steps))}

**Expected Result**: {test.expected_result}
"""
            )

        # Add results comment
        comment = f"""# CodeCapy Review ₍ᐢ•(ܫ)•ᐢ₎
- PR: #{pr.number}
- Commit: {pr.head.sha[:7]}

## Test Strategy
{generate_response.test_strategy}

## Setup Instructions
{generate_response.setup_instructions}

## Generated Test Cases
{chr(10).join(test_details)}

<details>
<summary>Raw Changes Analyzed</summary>

```diff
{file_changes_str}
```
</details>"""
        add_pr_comment(pr, comment)
        return generate_response

    except Exception as e:
        error_comment = f"""❌ Error while analyzing PR and generating tests:

```
{str(e)}
```
"""
        add_pr_comment(pr, error_comment)
        return None


class SetupSchema(BaseModel):
    setup_success: bool
    setup_error: Optional[str]


async def execute_tests(pr: PullRequest, gr: GenerateResponse, installation_id: int):
    """Execute the generated UI tests and report results."""
    add_pr_comment(pr, "🚀 Launching Scrapybara desktop...")

    scrapybara_client = Scrapybara(api_key=SCRAPYBARA_API_KEY)
    instance = None

    try:
        instance = scrapybara_client.start(instance_type="large")

        # Get repo details and access token
        repo_name = pr.base.repo.full_name
        access_token = get_installation_access_token(installation_id)
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
            add_pr_comment(
                pr,
                f"""⚠️ Error fetching GitHub variables, continuing setup: 
```
{str(e)}
```""",
            )

        # Get .capy content
        try:
            setup_instructions = pr.base.repo.get_contents(
                ".capy"
            ).decoded_content.decode()
        except Exception as e:
            setup_instructions = gr.setup_instructions

        # Run setup
        add_pr_comment(pr, "🔧 Setting up test environment...")
        setup_response = scrapybara_client.act(
            model=Anthropic(),
            tools=[
                BashTool(instance),
                ComputerTool(instance),
                EditTool(instance),
            ],
            system=SETUP_SYSTEM_PROMPT,
            prompt=f"""Here are the setup instructions:

{setup_instructions}

Available variables that have been set in the environment:
{chr(10).join(f'- {key}: {variables[key]}' for key in variables.keys())}

Please follow these instructions to set up the test environment in {repo_path}. The variables are already available in the environment, but you may need to create a .env file if the application requires it.""",
            schema=SetupSchema,
            on_step=lambda step: print(step),
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

        # Run tests
        test_results = []
        for i, test in enumerate(gr.tests, 1):
            add_pr_comment(pr, f"🧪 Running test {i}: {test.name}...")

            test_response = scrapybara_client.act(
                model=Anthropic(),
                tools=[
                    BashTool(instance),
                    ComputerTool(instance),
                    EditTool(instance),
                ],
                system=TEST_SYSTEM_PROMPT,
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
                on_step=lambda step: print(step.text),
            )

            # Format the result comment
            if test_response.success:
                result_comment = f"""✅ Test {i} Passed: {test.name}

{test_response.notes if test_response.notes else ""}

Screenshots taken during test:
"""
                for j, screenshot in enumerate(test_response.screenshots, 1):
                    result_comment += f"\nScreenshot {j}:\n<img src='data:image/png;base64,{screenshot}' />\n"
            else:
                result_comment = f"""❌ Test {i} Failed: {test.name}

Error: {test_response.error}
{test_response.notes if test_response.notes else ""}

Screenshots of failure:
"""
                for j, screenshot in enumerate(test_response.screenshots, 1):
                    result_comment += f"\nScreenshot {j}:\n<img src='data:image/png;base64,{screenshot}' />\n"

            add_pr_comment(pr, result_comment)
            test_results.append(test_response)

        # Summarize all test results
        passed_tests = sum(1 for r in test_results if r.success)
        total_tests = len(test_results)

        summary = f"""# Test Execution Summary 📊

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
    # finally:
    #     if instance:
    #         instance.stop()


@app.post("/webhooks/github")
async def github_webhook(request: Request):
    # Get raw payload first for signature verification
    payload = await request.body()
    verify_github_webhook(request, payload)

    # Parse the webhook payload
    data = GitHubWebhookPayload(**(await request.json()))

    # Handle PR events
    if "pull_request" in request.headers.get("X-GitHub-Event", ""):
        if data.action in ["opened", "synchronize"]:
            if not data.installation:
                raise HTTPException(
                    status_code=400, detail="No installation found in webhook payload"
                )

            installation_id = data.installation["id"]

            # Get installation access token
            access_token = get_installation_access_token(installation_id)

            # Initialize GitHub client with installation token
            g = Github(access_token)
            repo = g.get_repo(data.repository["full_name"])
            pr = repo.get_pull(data.pull_request["number"])

            # Process PR changes
            tests = await generate_tests(pr)
            if tests:
                await execute_tests(pr, tests, installation_id)

    return {"status": "ok"}


@app.get("/")
async def root():
    return {"status": "₍ᐢ-(ｪ)-ᐢ₎"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
