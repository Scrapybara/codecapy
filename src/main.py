from fastapi import FastAPI, Request, HTTPException
from fastapi.security import HTTPBearer
from github import Github

from .execute.config import ExecuteConfig
from .generate.config import GenerateConfig
from .github.models import GitHubWebhookPayload
from .github import verify_github_webhook, get_installation_access_token
from .generate import GenerateAgent
from .execute import ExecuteAgent

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

    # Parse the webhook payload
    data = GitHubWebhookPayload(**(await request.json()))

    # Only process pull request events
    if data.is_pull_request and data.action in ["opened", "synchronize"]:
        assert data.pull_request is not None
        if not data.installation or "id" not in data.installation:
            raise HTTPException(
                status_code=400, detail="No installation ID found in webhook payload"
            )

        installation_id = data.installation["id"]

        # Get installation access token
        access_token = get_installation_access_token(installation_id)

        # Initialize GitHub client with installation token
        github = Github(access_token)
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
