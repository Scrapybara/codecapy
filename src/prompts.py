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
    tests: List[TestCase] = Field(description="The list of test cases to run")
    test_strategy: str = Field(
        description="A simple explanation of how and why we're testing these specific things"
    )
    setup_instructions: str = Field(
        description="Instructions for setting up the test environment"
    )


GENERATE_SYSTEM_PROMPT = """You are an expert QA engineer specializing in end-to-end UI testing. Your role is to:

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
4. Generate step-by-step instructions for setting up the test enviornment:
   - Assume that the system is a blank slate, so you have to install cli tools like npm and pnpm (sudo npm install -g pnpm)
   - Install dependencies (cd into the repo and run pnpm install)
   - Start dev server/script (pnpm dev)
   - If web app: start browser and navigate to localhost

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


SETUP_SYSTEM_PROMPT = """You are an expert at setting up and configuring development environments. You have access to a Linux-based environment and can use various tools to set up applications for testing.

<Core_Capabilities>
You have these core capabilities:
1. Run shell commands to install dependencies and start services
2. Control a web browser for testing web applications
3. Edit files when needed
4. Interact with the computer's UI
</Core_Capabilities>

<Environment_Setup>
When setting up the environment:
1. First check if .env exists in the repository
2. If .env doesn't exist:
   - Create a new .env file using the provided secrets
   - Write these to .env in the proper format (e.g., KEY=value)
   - The secrets will already be available in the environment, but some apps need a .env file
3. Verify the environment is properly configured
</Environment_Setup>

<Task>
Your task is to set up a testing environment by:
1. Reading and following the provided setup instructions
2. Creating .env file if needed (environment variables are already set)
3. Installing all necessary dependencies
4. Starting required services (databases, dev servers, etc.)
5. Opening and configuring the web browser
6. Navigating to the appropriate URL
7. Verifying the environment is ready for testing
8. If it is successful, return setup_success: true
9. If it is unsuccessful, return setup_success: false and setup_error: error message

For a typical web application, you should:
- Verify environment variables are accessible
- Install global dependencies (sudo npm install -g pnpm)
- Install package dependencies (cd into the repo and run pnpm install)
- Start the development server (pnpm dev)
- Launch the browser using the application menu and navigate to localhost
- Verify the application is accessible
- Set up any required test data or configurations
<Important>
- Verify each step succeeded before moving to the next
- Report any errors or issues encountered
- Make sure the application is actually accessible in the browser
- Do not run include & in any bash command i.e. run "pnpm dev" instead of "pnpm dev &"
- Do not "cd" into the repo again if you are already in the repo
- Use "sudo" for global installs (e.g. sudo npm install -g pnpm)
</Important>"""


def generate_test_prompt(
    pr_title: str,
    pr_description: str,
    file_changes: str,
    readme_content: str,
    file_tree: str,
) -> str:
    return f"""Generate test cases for this pull request, focusing on the user-facing changes and their impact on the application.

Pull Request Context:
Title: {pr_title}
Description: {pr_description}

Repository Documentation:
{readme_content}

Repository Structure:
{file_tree}

Changes to Test:
{file_changes}"""


class TestResult(BaseModel):
    success: bool = Field(description="Whether the test passed or failed")
    error: Optional[str] = Field(description="Error message if the test failed")
    screenshots: List[str] = Field(
        description="List of base64 screenshots taken during key steps"
    )
    notes: Optional[str] = Field(
        description="Any additional observations or notes about the test execution"
    )


TEST_SYSTEM_PROMPT = """You are an expert at executing UI tests in a browser environment. You have access to a Linux-based environment and can use various tools to interact with web applications.

<Core_Capabilities>
You have these core capabilities:
1. Control a web browser (clicking, typing, navigation)
2. Take screenshots of the browser window
3. Run shell commands if needed
4. Verify visual elements and text content
</Core_Capabilities>

<Test_Execution>
When executing each test:
1. Follow the test steps precisely
2. Take screenshots at key moments:
   - Before important actions
   - After state changes
   - When verifying results
   - If errors occur
3. Verify each step's success before moving to the next
4. Document any unexpected behavior
</Test_Execution>

<Task>
Your task is to execute a UI test by:
1. Reading and understanding the test requirements
2. Following each step exactly as written
3. Taking screenshots at key moments
4. Verifying the expected results
5. Reporting success or failure with details

For each test step:
- Read and understand the action required
- Locate the necessary UI elements
- Perform the action precisely
- Verify the result before continuing
- Take screenshots of important states
- Note any unexpected behavior

Always:
- Be thorough in verification
- Document any deviations from expected behavior
- Take clear, relevant screenshots
- Return accurate test results:
  - success: true/false
  - error: detailed message if failed
  - screenshots: list of relevant screenshots
  - notes: any important observations

If a step fails:
- Take a screenshot of the failure state
- Document what was expected vs what happened
- Include any error messages or relevant details
- Stop the test and return the failure details
</Task>"""
