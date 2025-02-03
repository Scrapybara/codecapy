<div id="toc" align="center">
  <ul style="list-style: none">
    <summary>
      <h1>CodeCapy</h1>
    </summary>
  </ul>
</div>

<p align="center">
  The only PR bot that *actually* tests your code. CodeCapy is a GitHub app that automatically generates and runs natural language end-to-end UI tests for pull requests with Scrapybara VMs.
</p>

<p align="center">
  <a href="https://codecapy.ai"><img alt="Get started" src="https://img.shields.io/badge/Get%20started-codecapy.ai-blue" /></a>
</p>

## Features

- Automatically detects new PRs and PR updates
- Generates natural language tests based on PR changes using OpenAI models
- Executes tests in isolated Scrapybara VMs using Anthropic's Claude Computer Use capabilities
- Posts test results as PR comments

## Setup

### Prerequisites

- Python 3.9+
- Poetry for dependency management
- A GitHub account with permissions to create GitHub Apps
- Scrapybara API key
- OpenAI API key (for test generation)
- Anthropic API key (for test execution)

### Installation

1. Clone the repository:

```bash
git clone https://github.com/scrapybara/codecapy.git
cd codecapy
```

2. Install dependencies:

```bash
poetry install
```

3. Create a GitHub App:

   - Go to GitHub Settings > Developer Settings > GitHub Apps
   - Create a new GitHub App with the following permissions:
     - Pull requests: Read & Write
     - Contents: Read
     - Metadata: Read
   - Generate and download a private key
   - Note your GitHub App ID and webhook secret

4. Set up environment variables:

```bash
cp .env.example .env
```

Edit `.env` with your:

- GitHub App ID
- GitHub Private Key
- GitHub Webhook Secret
- Scrapybara API Key
- OpenAI API Key
- Anthropic API Key (optional, will use Scrapybara agent credit if not provided)

### Configuration

The bot uses two main agents that can be configured in `main.py`:

#### Generate Agent (OpenAI)

The Generate Agent handles test generation using OpenAI models. It can be configured with different models and system prompts for each step:

```python
generate_agent = GenerateAgent(
    config=GenerateConfig(
        analyze_files=GenerateStepConfig(
            model="o3-mini",  # Available models: o3-mini, o1, o1-mini, gpt-4o, gpt-4o-mini
            system_prompt=ANALYZE_FILES_SYSTEM_PROMPT,
        ),
        summarize_file=GenerateStepConfig(
            model="gpt-4o-mini",
            system_prompt=SUMMARIZE_FILE_SYSTEM_PROMPT,
        ),
        generate_tests=GenerateStepConfig(
            model="o3-mini",
            system_prompt=GENERATE_TESTS_SYSTEM_PROMPT,
        ),
    )
)
```

_More generate models will be supported in the future._

#### Execute Agent (Scrapybara Act SDK)

The Execute Agent runs tests using Scrapybara VMs and Anthropic's Claude Computer Use. It can be configured with different system prompts for each step:

```python
execute_agent = ExecuteAgent(
    config=ExecuteConfig(
        auto_setup=ExecuteStepConfig(
            model="claude-3-5-sonnet-20241022",  # Available models: claude-3-5-sonnet-20241022
            system_prompt=auto_setup_system_prompt,
        ),
        instruction_setup=ExecuteStepConfig(
            model="claude-3-5-sonnet-20241022",
            system_prompt=instruction_setup_system_prompt,
        ),
        execute_test=ExecuteStepConfig(
            model="claude-3-5-sonnet-20241022",
            system_prompt=execute_test_system_prompt,
        ),
    )
)
```

_More execute models will be supported as Scrapybara Act SDK supports more models._

### Running the bot

1. Start the FastAPI server:

```bash
poetry run uvicorn src.main:app --reload
```

2. Set up webhook forwarding (for local development):

   - Use ngrok or similar to expose your local server
   - Update your GitHub App's webhook URL to point to your exposed endpoint

3. Install the GitHub App on your repositories

## Test Configuration

You can configure test execution behavior using a `capy.yaml` file in your repository:

```yaml
steps:
  - type: bash
    command: "npm install"
  - type: create-env
  - type: instruction
    text: "Set up the development environment"
  - type: wait
    seconds: 10
```

## Development

- Format code: `poetry run black .`
- Type checking: `poetry run mypy`
- Run tests: `poetry run pytest`

## License

MIT
