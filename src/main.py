from typing import Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.security import HTTPBearer
from github import Github
from datetime import datetime

from .execute.config import ExecuteConfig
from .generate.config import GenerateConfig
from .github.models import GitHubWebhookPayload
from .github import (
    get_installation,
    verify_github_webhook,
    get_installation_access_token,
)
from .generate import GenerateAgent
from .execute import ExecuteAgent
from .database import (
    upsert_repo,
    get_repos_by_installation_id,
    disconnect_repos,
    upsert_review,
)
from .models import Review

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
        "pull_request",
    ]:
        if not data.installation or "id" not in data.installation:
            raise HTTPException(
                status_code=400, detail="No installation ID found in webhook payload"
            )
        installation_id = data.installation["id"]

        # Skip access token retrieval for installation deletion
        if event_type == "installation" and data.action in ["deleted", "suspend"]:
            db_repos = get_repos_by_installation_id(installation_id)
            if db_repos:
                # Disconnect all stored repos for the given installation
                removed_repo_ids = [repo.id for repo in db_repos]
                disconnect_repos(removed_repo_ids)
            return {"status": "ok"}

        access_token = get_installation_access_token(installation_id)
        github = Github(access_token)

    # Handle installation events
    if event_type == "installation":
        # Get all repositories for this installation
        installation = get_installation(installation_id)
        repos = installation.get_repos()

        if data.action in ["created", "unsuspend"]:
            # Add each repository to database
            for repo in repos:
                upsert_repo(repo.raw_data, installation_id, True)

    # Handle repository events
    elif event_type == "installation_repositories":
        # Get all repositories for this installation
        installation = get_installation(installation_id)
        repos = installation.get_repos()

        if data.action == "added":
            # Add each repository to database
            for repo in repos:
                upsert_repo(repo.raw_data, installation_id, True)
        elif data.action == "removed":
            # Get all repos from database for this installation
            db_repos = get_repos_by_installation_id(installation_id)
            if db_repos:
                # Get current repo IDs from GitHub
                current_repo_ids = [repo.id for repo in repos]
                # Find repos that are in DB but no longer in GitHub
                removed_repo_ids = [
                    repo.id for repo in db_repos if repo.id not in current_repo_ids
                ]
                # Disconnect removed repos
                if removed_repo_ids:
                    disconnect_repos(removed_repo_ids)

    elif event_type == "repository":
        # Handle repository metadata changes
        if (
            data.action
            in ["edited", "renamed", "transferred", "publicized", "privatized"]
            and data.repository
        ):
            # Update repository in database with latest data
            repo = github.get_repo(data.repository["full_name"])
            upsert_repo(repo.raw_data, installation_id)
        elif data.action == "deleted" and data.repository:
            disconnect_repos([data.repository["id"]])

    # Handle pull request events
    elif event_type == "pull_request" and data.action in ["opened", "synchronize"]:
        assert data.pull_request is not None and data.repository is not None

        # Get the pull request object
        repo = github.get_repo(data.repository["full_name"])
        pr = repo.get_pull(data.pull_request["number"])

        # Create review if we have a database
        current_time = datetime.now().isoformat()
        pending_review = Review.create_pending(
            repo_id=data.repository["id"],
            pr_number=pr.number,
            commit_sha=pr.head.sha,
            current_time=current_time,
        )
        review = upsert_review(pending_review)

        # Generate tests
        gr = await generate_agent.generate_tests(pr, review)

        # Execute tests if we have them
        if gr:
            await execute_agent.execute_tests(pr, gr, access_token, review)

    return {"status": "ok"}


@app.get("/")
async def root():
    return {"status": "₍ᐢ-(ｪ)-ᐢ₎"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
