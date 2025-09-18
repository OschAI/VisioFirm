"""
Client authentication for Python wrappers using API keys.
Usage: VF.login('username', 'your_api_key_here')
Sets global current_user_id for injection into Project/wrappers.
"""

from visiofirm.models.user import get_user_by_api_key

current_user_id = None  # Global: Set by login, used by wrappers/Project methods

def login(identifier: str, api_key: str) -> bool:
    """
    Authenticate via API key (from profile).
    Verifies api_key matches user, and identifier == username or email.
    Returns True if successful; sets current_user_id.
    """
    global current_user_id
    user = get_user_by_api_key(api_key)
    if not user or not user[7]:  # user[7] == api_key (ensure not None)
        return False
    # Match identifier to username (user[1]) or email (user[5])
    if identifier != user[1] and identifier != user[5]:
        return False
    current_user_id = user[0]  # user_id
    return True

def logout():
    """Clear auth state."""
    global current_user_id
    current_user_id = None

def get_current_user_id() -> int | None:
    """Helper: Get current user ID (for debugging)."""
    global current_user_id
    return current_user_id