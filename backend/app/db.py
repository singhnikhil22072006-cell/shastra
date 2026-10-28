from supabase import create_client

from .config import settings

# Service-role client: bypasses RLS, so every query MUST filter by the verified user id.
sb = create_client(settings.supabase_url, settings.supabase_service_role_key)
