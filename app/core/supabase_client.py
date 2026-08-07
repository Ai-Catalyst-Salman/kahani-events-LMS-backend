"""
app/core/supabase_client.py
---------------------------
Lazily creates the Supabase client using the SERVICE ROLE key.

The client is created on first access (not at module import time).
This allows test suites to mock the client before the first real call,
and also allows the app to start up without a valid key during testing.

The service role key bypasses Row Level Security, so this client must
ONLY be used server-side after the application layer has verified the
caller's identity. It must never be exposed to or used by the frontend.
"""

from supabase import create_client, Client
from app.core.config import settings

_supabase_client: Client | None = None


def _get_client() -> Client:
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
    return _supabase_client


class _LazySupabaseProxy:
    """
    Proxy object that creates the real Supabase client on first attribute access.
    This allows the module-level `supabase` object to be imported and then
    replaced by mocks in tests without triggering client construction at import time.
    """

    def __getattr__(self, name):
        return getattr(_get_client(), name)


supabase: Client = _LazySupabaseProxy()  # type: ignore[assignment]
