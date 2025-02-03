from fastapi import FastAPI, Request, HTTPException
from fastapi.security import HTTPBearer
from github import Github

from .execute.config import ExecuteConfig
from .generate.config import GenerateConfig
from .github.models import GitHubWebhookPayload
from .github import verify_github_webhook, get_installation_access_token
from .generate import GenerateAgent
from .execute import ExecuteAgent
from .database import upsert_repository, delete_repository

# Initialize FastAPI app
app = FastAPI()
security = HTTPBearer()

# Initialize agents
# Note: you can configure your agents here!
generate_agent = GenerateAgent(config=GenerateConfig())
execute_agent = ExecuteAgent(config=ExecuteConfig())


@app.post("/webhooks/github")
async def github_webhook(request: Request):
    # Get raw payload first for signature verification
    payload = await request.body()
    verify_github_webhook(request, payload)

    # Get event type from header
    event_type = request.headers.get("X-GitHub-Event", "")

    # Parse the webhook payload
    data = GitHubWebhookPayload(**(await request.json()))

    # Validate installation ID for events that require it
    if event_type in [
        "installation",
        "installation_repositories",
        "repository",
        "installation_target",
        "pull_request",
    ]:
        if not data.installation or "id" not in data.installation:
            raise HTTPException(
                status_code=400, detail="No installation ID found in webhook payload"
            )
        installation_id = data.installation["id"]
        access_token = get_installation_access_token(installation_id)
        github = Github(access_token)

    # Handle installation events
    if event_type == "installation":
        if data.action == "created":
            # Add all repositories to database
            for repo_data in data.repositories or []:
                repo = github.get_repo(repo_data["full_name"])
                upsert_repository(repo.raw_data)
        elif data.action == "deleted":
            # Remove all repositories from database
            for repo_data in data.repositories or []:
                delete_repository(repo_data["id"])

    # Handle repository events
    elif event_type == "installation_repositories":
        # Handle repositories being added/removed from installation
        if data.action == "added" and data.repository:
            # Add repository to database
            repo = github.get_repo(data.repository["full_name"])
            upsert_repository(repo.raw_data)
        elif data.action == "removed" and data.repository:
            # Remove repository from database
            delete_repository(data.repository["id"])

    elif event_type == "repository":
        # Handle repository metadata changes
        if (
            data.action
            in ["edited", "renamed", "transferred", "publicized", "privatized"]
            and data.repository
        ):
            # Update repository in database with latest data
            repo = github.get_repo(data.repository["full_name"])
            upsert_repository(repo.raw_data)
        elif data.action == "deleted" and data.repository:
            # Remove repository from database
            delete_repository(data.repository["id"])

    # Handle installation target changes
    elif event_type == "installation_target":
        # Update all repositories for this installation to reflect new ownership
        if data.repositories:
            for repo_data in data.repositories:
                repo = github.get_repo(repo_data["full_name"])
                upsert_repository(repo.raw_data)

    # Handle pull request events
    elif event_type == "pull_request" and data.action in ["opened", "synchronize"]:
        assert data.pull_request is not None and data.repository is not None

        # Get the pull request object
        repo = github.get_repo(data.repository["full_name"])
        pr = repo.get_pull(data.pull_request["number"])

        # Process PR changes
        tests = await generate_agent.generate_tests(pr)
        if tests:
            await execute_agent.execute_tests(pr, tests, access_token)

    return {"status": "ok"}


@app.get("/")
async def root():
    return {"status": "₍ᐢ-(ｪ)-ᐢ₎"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
