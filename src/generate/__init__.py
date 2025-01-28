from typing import Optional
from openai import OpenAI
from github.PullRequest import PullRequest
import yaml
import asyncio
from concurrent.futures import ThreadPoolExecutor

from src.models import CapyConfig
from ..config import OPENAI_API_KEY
from ..github import add_pr_comment, edit_pr_comment, get_tree_content
from .models import GenerateResponse, FileAnalysisResponse
from .prompts import (
    GENERATE_SYSTEM_PROMPT,
    generate_test_prompt,
    ANALYZE_SYSTEM_PROMPT,
    generate_file_analysis_prompt,
)


async def summarize_file(repo, file, openai_client, pr):
    """Summarize a single file asynchronously."""
    try:
        content = repo.get_contents(file.path, ref=pr.head.ref)
        if isinstance(content, list):
            return f"## {file.path}\nError: File is a directory\n"
        file_content = content.decoded_content.decode()

        # Summarize file with 4o-mini
        completion = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert code analyst. Provide a concise 2 sentence summary of this file's purpose and key functionality.",
                },
                {
                    "role": "user",
                    "content": f"File: {file.path}\n\nContent:\n{file_content}",
                },
            ],
        )

        summary = completion.choices[0].message.content
        print(summary)
        return f"## {file.path}\nReason for importance: {file.reason}\nSummary: {summary}\n"
    except Exception as e:
        return f"## {file.path}\nError reading file: {str(e)}\n"


async def generate_tests(pr: PullRequest) -> Optional[GenerateResponse]:
    """Process PR changes and generate test cases."""
    # Add initial comment that we're processing the PR
    summary_comment_id = add_pr_comment(
        pr, "🔍 Analyzing PR changes and preparing to run tests..."
    )

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

        # Get file tree and analyze important files
        file_tree = get_tree_content(repo)

        # Analyze file tree with 4o
        analyze_completion = openai_client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": ANALYZE_SYSTEM_PROMPT},
                {"role": "user", "content": generate_file_analysis_prompt(file_tree)},
            ],
            response_format=FileAnalysisResponse,
        )

        file_analysis = FileAnalysisResponse.model_validate(
            analyze_completion.choices[0].message.parsed
        )
        print(file_analysis)

        # Get content and summarize important files in parallel
        tasks = [
            summarize_file(repo, file, openai_client, pr)
            for file in file_analysis.files
        ]
        important_file_summaries = await asyncio.gather(*tasks)

        # Join all summaries
        codebase_context = "\n".join(important_file_summaries)

        # Get README content
        try:
            content = repo.get_contents("README.md", ref=pr.head.ref)
            if isinstance(content, list):
                raise ValueError("README.md should not be a directory")
            readme_content = content.decoded_content.decode()
        except Exception as e:
            readme_content = f"Error reading README: {str(e)}"

        # Get capy.yaml content
        try:
            content = pr.base.repo.get_contents("capy.yaml", ref=pr.head.ref)
            if isinstance(content, list):
                raise ValueError("capy.yaml should not be a directory")
            capy_content = content.decoded_content.decode()
            capy_config = CapyConfig.model_validate(yaml.safe_load(capy_content))
        except Exception:
            capy_config = None

        # Generate the test prompt with enhanced context
        test_prompt = generate_test_prompt(
            pr_title=pr_title,
            pr_description=pr_description,
            file_changes=file_changes_str,
            readme_content=readme_content,
            file_tree=file_tree,
            capy_config=capy_config,
            codebase_context=codebase_context,
        )

        # Generate test cases with o1
        generate_completion = openai_client.beta.chat.completions.parse(
            model="o1",
            messages=[
                {"role": "system", "content": GENERATE_SYSTEM_PROMPT},
                {"role": "user", "content": test_prompt},
            ],
            response_format=GenerateResponse,
        )

        # Parse the test cases
        generate_response = GenerateResponse.model_validate(
            generate_completion.choices[0].message.parsed
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

## Codebase Summary
{generate_response.codebase_summary}

## PR Changes
{generate_response.pr_changes}

## Setup Instructions
{"Fetched from capy.yaml" if capy_config else generate_response.setup_instructions}

## Generated Test Cases
{chr(10).join(test_details)}

<details>
<summary>Raw Changes Analyzed</summary>

```diff
{file_changes_str}
```
</details>"""
        if summary_comment_id:
            edit_pr_comment(pr, summary_comment_id, comment)
        return generate_response

    except Exception as e:
        error_comment = f"""❌ Error while analyzing PR and generating tests:

```
{str(e)}
```
"""
        if summary_comment_id:
            edit_pr_comment(pr, summary_comment_id, error_comment)
        return None
