from typing import Optional
import hmac
import hashlib
from fastapi import HTTPException, Request
from github import GithubIntegration
from github.PullRequest import PullRequest
from github.IssueComment import IssueComment
from ..config import settings


def get_github_integration() -> GithubIntegration:
    """Create GitHub Integration instance."""
    return GithubIntegration(
        integration_id=settings.github_app_id,
        private_key=settings.github_private_key,
    )


def get_installation_access_token(installation_id: int) -> str:
    """Get an access token for a GitHub App installation."""
    integration = get_github_integration()
    access_token = integration.get_access_token(installation_id)
    return access_token.token


def verify_github_webhook(request: Request, payload: Optional[bytes] = None) -> None:
    """Verify GitHub webhook signature."""
    if not settings.github_webhook_secret:
        raise HTTPException(
            status_code=500, detail="GitHub webhook secret not configured"
        )

    signature = request.headers.get("X-Hub-Signature-256")
    if not signature:
        raise HTTPException(status_code=400, detail="No signature header found")

    hash_object = hmac.new(
        settings.github_webhook_secret.encode("utf-8"),
        msg=payload,
        digestmod=hashlib.sha256,
    )
    expected_signature = f"sha256={hash_object.hexdigest()}"

    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")


def add_pr_comment(pr: PullRequest, comment_text: str) -> Optional[int]:
    """Add a comment to a pull request and return its ID."""
    try:
        comment: IssueComment = pr.create_issue_comment(comment_text)
        return comment.id
    except Exception as e:
        print(f"Error adding comment to PR: {e}")
        return None


def edit_pr_comment(pr: PullRequest, comment_id: int, new_comment: str) -> bool:
    """Edit an existing PR comment."""
    try:
        comment = pr.get_issue_comment(comment_id)
        comment.edit(new_comment)
        return True
    except Exception as e:
        print(f"Error editing PR comment: {e}")
        return False


def get_tree_content(repo, path: str = "", level: int = 0, max_level: int = 3) -> str:
    """Get repository file tree content."""
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
                    subtree = get_tree_content(repo, content.path, level + 1, max_level)
                    if subtree:
                        tree.append(f"{'  ' * level}📁 {content.name}/\n" + subtree)
            else:
                if not content.name.startswith(".") and not content.name.endswith(
                    (".pyc", ".pyo")
                ):
                    tree.append(f"{'  ' * level}📄 {content.name}")
        return "\n".join(tree)
    except Exception as e:
        return f"Error getting tree for {path}: {str(e)}"
