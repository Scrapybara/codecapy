from datetime import datetime
from typing import Optional, Dict, Any
from supabase import create_client, Client
from .config import settings

supabase: Optional[Client] = (
    create_client(settings.supabase_url, settings.supabase_key)
    if settings.supabase_url and settings.supabase_key
    else None
)


def upsert_repository(
    repo_data: Dict[str, Any], installation_id: int, connected: Optional[bool] = None
) -> Optional[Dict[str, Any]]:
    """
    Insert or update a repository in the database.
    Returns the inserted/updated repository data or None if database is not configured.
    """
    if not supabase:
        return None

    try:
        data = {
            "id": repo_data["id"],
            "owner_github_id": repo_data["owner"]["id"],
            "installation_id": installation_id,
            "name": repo_data["name"],
            "owner": repo_data["owner"]["login"],
            "owner_avatar_url": repo_data["owner"]["avatar_url"],
            "url": repo_data["html_url"],
            "is_private": repo_data["private"],
            "updated_at": datetime.now().isoformat(),
        }
        if connected is not None:
            data["connected"] = connected
        result = supabase.table("repos").upsert(data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"Error upserting repository: {e}")
        return None


def get_repos_by_installation_id(
    installation_id: int,
) -> Optional[list[Dict[str, Any]]]:
    """
    Get all repositories for a given installation ID.
    Returns a list of repository data or None if database is not configured.
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
        return result.data if result.data else []
    except Exception as e:
        print(f"Error getting repositories: {e}")
        return None


def disconnect_repositories(repo_ids: list[int]) -> Optional[list[Dict[str, Any]]]:
    """
    Set the connected status to false for the given repository IDs.
    Returns the updated repository data or None if database is not configured.
    """
    if not supabase:
        return None

    try:
        data = {
            "connected": False,
            "updated_at": datetime.now().isoformat(),
        }
        result = supabase.table("repos").update(data).in_("id", repo_ids).execute()
        return result.data if result.data else None
    except Exception as e:
        print(f"Error disconnecting repositories: {e}")
        return None
