from typing import List, Optional
from ..models import TimestampedStep


def format_agent_steps(steps: List[TimestampedStep]) -> str:
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


def setup_in_progress_comment(steps: List[TimestampedStep]) -> str:
    return f"""🔧 Setting up test environment...

<details>
<summary>Agent Steps</summary>

{format_agent_steps(steps)}
</details>"""


def setup_error_comment(error: Optional[str]) -> str:
    return f"""❌ Error setting up test environment: 
```
{error}
```"""


def setup_error_with_steps_comment(
    error: Optional[str], steps: List[TimestampedStep]
) -> str:
    return f"""❌ Error setting up test environment: 
```
{error}
```

<details>
<summary>Agent Steps</summary>

{format_agent_steps(steps)}
</details>"""


def setup_complete_comment(steps: List[TimestampedStep]) -> str:
    return f"""✅ Setup complete! Running tests...

<details>
<summary>Agent Steps</summary>

{format_agent_steps(steps)}
</details>"""


def test_starting_comment(test_number: int, test_name: str) -> str:
    return f"🧪 Running test {test_number}: {test_name}..."


def test_in_progress_comment(
    test_number: int, test_name: str, steps: List[TimestampedStep]
) -> str:
    return f"""🧪 Running test {test_number}: {test_name}...

<details>
<summary>Agent Steps</summary>

{format_agent_steps(steps)}
</details>"""


def test_result_comment(
    test_number: int,
    test_name: str,
    success: bool,
    error: str | None,
    notes: str | None,
    steps: List[TimestampedStep],
) -> str:
    status = "✅ Passed" if success else "❌ Failed"
    error_section = f"\nError: {error}" if error else ""
    notes_section = f"\n{notes}" if notes else ""

    return f"""{status}: Test {test_number}: {test_name}
{error_section}{notes_section}

<details>
<summary>Agent Steps</summary>

{format_agent_steps(steps)}
</details>"""


def test_summary_comment(passed_tests: int, total_tests: int) -> str:
    all_passed = passed_tests == total_tests
    status = (
        "🎉 All tests passed!"
        if all_passed
        else "⚠️ Some tests failed. Please check the individual test results above for details."
    )

    return f"""# CodeCapy Test Results 📊

{passed_tests}/{total_tests} tests passed

{status}"""


def launching_desktop_comment() -> str:
    return "🚀 Launching Scrapybara desktop..."


def launching_desktop_error_comment(error: str) -> str:
    return f"""🚀 Launching Scrapybara desktop...

⚠️ Error fetching GitHub variables, continuing setup: 
```
{error}
```"""
