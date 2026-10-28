from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    supabase_url: str
    supabase_service_role_key: str
    supabase_bucket: str = "documents"
    frontend_origin: str = "http://localhost:5173"
    max_upload_mb: int = 10
    max_pages: int = 8
    # Comma-separated e-mails that become ADMIN on first login (only if the e-mail is confirmed).
    admin_emails: str = ""
    # QR codes that carry a URL are compared against these hosts. CONFIRM the list with AICTE before relying on it.
    official_domains: str = "aicte-india.org,aicte.gov.in"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def admin_list(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @property
    def domain_list(self) -> list[str]:
        return [d.strip().lower() for d in self.official_domains.split(",") if d.strip()]


settings = Settings()
