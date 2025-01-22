from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.security import HTTPBearer
from github import Github, GithubIntegration
from github.PullRequest import PullRequest
from scrapybara import Scrapybara
from scrapybara.anthropic import Anthropic
from scrapybara.tools import ComputerTool, BashTool, EditTool, BrowserTool
from pydantic import BaseModel
from typing import List, Optional
import hmac
import hashlib
import os
from dotenv import load_dotenv
from pydantic import BaseModel
from openai import OpenAI
from .prompts import TestCase, TestsSchema, SYSTEM_PROMPT, generate_test_prompt

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


async def generate_tests(pr: PullRequest) -> Optional[List[TestCase]]:
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

        # Get summaries of largest/most important files
        important_files = []
        for content in repo.get_contents(""):
            if content.type == "file" and content.name.endswith(
                (
                    ".py",
                    ".js",
                    ".ts",
                    ".tsx",
                    ".go",
                    ".rs",
                    ".jsx",
                    ".vue",
                    ".svelte",
                    ".java",
                    ".kt",
                    ".rb",
                    ".php",
                    ".cs",
                    ".cpp",
                    ".c",
                    ".h",
                    ".hpp",
                    ".scala",
                    ".swift",
                    ".m",
                    ".mm",
                    ".dart",
                    ".ex",
                    ".exs",
                    ".erl",
                    ".hs",
                    ".fs",
                    ".fsx",
                    ".ml",
                    ".mli",
                    ".clj",
                    ".cljc",
                    ".cljs",
                    ".html",
                    ".htm",
                    ".css",
                    ".scss",
                    ".sass",
                    ".less",
                    ".styl",
                )
            ):
                file_content = content.decoded_content.decode()
                line_count = len(file_content.splitlines())
                if line_count > 500:  # Only summarize files with >500 lines
                    summary_completion = openai_client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {
                                "role": "system",
                                "content": "You are a code analysis expert. Provide a brief 1-2 sentence summary of this file's purpose and main functionality.",
                            },
                            {
                                "role": "user",
                                "content": f"File: {content.name}\n\nContent:\n{file_content}",
                            },
                        ],
                        max_tokens=150,
                    )
                    summary = summary_completion.choices[0].message.content
                    important_files.append(
                        f"File: {content.name}\nSummary: {summary}\n"
                    )

        # Generate the test prompt with enhanced context
        test_prompt = generate_test_prompt(
            pr_title=pr_title,
            pr_description=pr_description,
            file_changes=file_changes_str,
            readme_content=readme_content,
            file_tree=file_tree,
            important_files="\n".join(important_files),
        )

        print(test_prompt)

        # Generate test cases
        completion = openai_client.beta.chat.completions.parse(
            model="o1-2024-12-17",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": test_prompt},
            ],
            response_format=TestsSchema,
        )

        # Parse the test cases
        tests_parsed = TestsSchema.model_validate(completion.choices[0].message.parsed)

        # Format test results for the comment
        test_details = []
        for i, test in enumerate(tests_parsed.tests, 1):
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
- Coverage Focus: {', '.join(tests_parsed.coverage_focus)}

## Test Strategy
{tests_parsed.test_strategy}

## Generated Test Cases
{chr(10).join(test_details)}

<details>
<summary>Raw Changes Analyzed</summary>

```diff
{file_changes_str}
```
</details>"""
        add_pr_comment(pr, comment)
        return tests_parsed.tests

    except Exception as e:
        error_comment = f"""❌ Error while analyzing PR and generating tests:

```
{str(e)}
```
"""
        add_pr_comment(pr, error_comment)
        return None


async def execute_tests(pr: PullRequest, tests: List[TestCase]):
    """Execute the generated UI tests and report results."""
    add_pr_comment(pr, "🚀 Running tests...")

    # TODO: Implement actual test execution logic


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

            # Get installation access token
            access_token = get_installation_access_token(data.installation["id"])

            # Initialize GitHub client with installation token
            g = Github(access_token)
            repo = g.get_repo(data.repository["full_name"])
            pr = repo.get_pull(data.pull_request["number"])

            # Process PR changes
            tests = await generate_tests(pr)
            if tests:
                await execute_tests(pr, tests)

    return {"status": "ok"}


@app.get("/")
async def root():
    return {"status": "₍ᐢ-(ｪ)-ᐢ₎"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
