from typing import List, Literal
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


class TestsSchema(BaseModel):
    tests: List[TestCase] = Field(description="The list of test cases to run")
    coverage_focus: List[str] = Field(
        description="The main parts of the website these tests check"
    )
    test_strategy: str = Field(
        description="A simple explanation of how and why we're testing these specific things"
    )


SYSTEM_PROMPT = """You are an expert QA engineer specializing in end-to-end UI testing. Your role is to:

1. Analyze UI changes and user workflows in pull requests
2. Understand the user-facing functionality of the application
3. Generate comprehensive UI test scenarios that:
   - Cover complete user journeys and workflows
   - Test common user interactions and navigation
   - Verify the visual appearance and layout
   - Check behavior across different browsers
   - Test how errors are shown to users
   - Verify user data is saved correctly
   - Test accessibility features
   - Check if the app feels fast and responsive

For each test case:
- Give it a clear, descriptive name
- Explain which part of the user experience it tests
- List what needs to be set up first (like being logged in)
- Write clear steps anyone can follow (e.g. "Click the blue 'Submit' button")
- Describe exactly what the user should see happen
- Mention any cleanup needed
- Mark how important the test is

Consider:
- Testing in different browsers
- How it looks on phones vs computers
- Whether it's easy to use for everyone
- If anything looks broken or different
- Clear error messages for users
- Pages loading quickly
- Information being saved correctly
- Moving between different pages
- Forms working correctly
- Backend operations visible to users

Your output should be in clear, natural language that any person who can use a website would understand. Avoid technical jargon - write as if explaining to a friend how to test a website."""


def generate_test_prompt(
    pr_title: str,
    pr_description: str,
    file_changes: str,
    readme_content: str,
    file_tree: str,
    important_files: str,
) -> str:
    return f"""Generate test cases for this pull request, focusing on the user-facing changes and their impact on the application.

Pull Request Context:
Title: {pr_title}
Description: {pr_description}

Repository Documentation:
{readme_content}

Repository Structure:
{file_tree}

Key Files Analysis:
{important_files}

Changes to Test:
{file_changes}"""
