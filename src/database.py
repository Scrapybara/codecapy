from datetime import datetime
from typing import Optional, Dict, Any, List
from supabase import create_client, Client
from .config import settings
from .models import Review, Repo

supabase: Optional[Client] = (
    create_client(settings.supabase_url, settings.supabase_key)
    if settings.supabase_url and settings.supabase_key
    else None
)


def upsert_repo(
    repo_data: Dict[str, Any], installation_id: int, connected: Optional[bool] = None
) -> Optional[Repo]:
    """
    Insert or update a repository in the database.
    Returns the inserted/updated repository or None if database is not configured.
    """
    if not supabase:
        return None

    try:
        # Create Repo instance from GitHub data
        repo = Repo.from_github_data(repo_data, installation_id, connected)

        # Convert to dict for database
        data = repo.model_dump(exclude_none=True)

        # Upsert the repository
        result = supabase.table("repos").upsert(data).execute()
        if not result.data:
            return None

        # Convert result back to Repo object
        return Repo.model_validate(result.data[0])
    except Exception as e:
        print(f"Error upserting repository: {e}")
        return None


def get_repos_by_installation_id(installation_id: int) -> Optional[List[Repo]]:
    """
    Get all repositories for a given installation ID.
    Returns a list of repositories or None if database is not configured.
    """
    if not supabase:
        return None

    try:
        result = (
            supabase.table("repos")
            .select("*")
            .eq("installation_id", installation_id)
            .execute()
        )
        if not result.data:
            return []

        # Convert results to Repo objects
        return [Repo.model_validate(repo_data) for repo_data in result.data]
    except Exception as e:
        print(f"Error getting repositories: {e}")
        return None


def disconnect_repos(repo_ids: List[int]) -> Optional[List[Repo]]:
    """
    Set the connected status to false for the given repository IDs.
    Returns the updated repositories or None if database is not configured.
    """
    if not supabase:
        return None

    try:
        data = {
            "connected": False,
            "updated_at": datetime.now().isoformat(),
        }
        result = supabase.table("repos").update(data).in_("id", repo_ids).execute()
        if not result.data:
            return None

        # Convert results to Repo objects
        return [Repo.model_validate(repo_data) for repo_data in result.data]
    except Exception as e:
        print(f"Error disconnecting repositories: {e}")
        return None


def upsert_review(review: Review) -> Optional[Review]:
    """
    Insert or update a review in the database.
    If review.id is None, a new review will be created.
    Returns the inserted/updated review or None if database is not configured.
    """
    if not supabase:
        return None

    try:
        # Convert review to dict, preserving nested structure
        data = review.model_dump(exclude_none=True)
        data["updated_at"] = datetime.now().isoformat()

        # Upsert the review
        result = supabase.table("reviews").upsert(data).execute()

        if not result.data:
            return None

        # Convert the result back to a Review object
        return Review.model_validate(result.data[0])
    except Exception as e:
        print(f"Error upserting review: {e}")
        return None
