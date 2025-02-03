from datetime import datetime
from typing import Optional, Dict, Any
from supabase import create_client, Client
from .config import settings

supabase: Optional[Client] = (
    create_client(settings.supabase_url, settings.supabase_key)
    if settings.supabase_url and settings.supabase_key
    else None
)


def upsert_repository(repo_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
            "name": repo_data["name"],
            "owner": repo_data["owner"]["login"],
            "owner_avatar_url": repo_data["owner"]["avatar_url"],
            "url": repo_data["html_url"],
            "is_private": repo_data["private"],
            "updated_at": datetime.now().isoformat(),
        }
        result = supabase.table("repos").upsert(data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        print(f"Error upserting repository: {e}")
        return None


def delete_repository(github_id: int) -> bool:
    """
    Soft delete a repository from the database by setting its deleted flag to True.
    Returns True if successful, False if database is not configured or update failed.
    """
    if not supabase:
        return False

    try:
        supabase.table("repos").update({"deleted": True}).eq(
            "github_id", github_id
        ).execute()
        return True
    except Exception as e:
        print(f"Error deleting repository: {e}")
        return False
