# PR Test Bot

A GitHub App that automatically generates and runs natural language tests for Pull Requests using Scrapybara VMs.

## Features

- Automatically detects new PRs and PR updates
- Generates natural language tests based on PR changes using LLMs
- Runs tests in isolated Scrapybara VMs
- Posts test results as PR comments

## Setup

### Prerequisites

- Python 3.9+
- Poetry for dependency management
- A GitHub account with permissions to create GitHub Apps
- Scrapybara API key
- Anthropic API key (for LLM-based test generation)

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
- Anthropic API Key (optional)

### Running the Bot

1. Start the FastAPI server:

```bash
poetry run uvicorn src.main:app --reload
```

2. Set up webhook forwarding (for local development):

   - Use ngrok or similar to expose your local server
   - Update your GitHub App's webhook URL to point to your exposed endpoint

3. Install the GitHub App on your repositories

## Usage

The bot automatically:

1. Detects new PRs and PR updates
2. Analyzes the changes
3. Generates appropriate tests
4. Runs tests in Scrapybara VMs
5. Posts results as PR comments

## Development

- Format code: `poetry run black .`
- Type checking: `poetry run mypy`
- Run tests: `poetry run pytest`

## License

MIT
