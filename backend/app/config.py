from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    app_name: str = "FactoryLink"
    log_level: str = "INFO"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://factorylink:factorylink_local@db:5432/factorylink"
    jwt_secret_key: str = "local-development-only-change-this-secret-before-deployment"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 20
    refresh_token_days: int = 14
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    redis_url: str = "redis://redis:6379/0"
    auto_create_schema: bool = False
    seed_demo_data: bool = True
    allow_public_registration: bool = True
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "FactoryLink <no-reply@factorylink.local>"
    smtp_starttls: bool = True
    # Optional HTTPS delivery channel; when set it takes precedence over SMTP.
    resend_api_key: str = ""
    resend_from: str = ""
    # Google sign-in. Leave both values empty to disable the Google button.
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""
    # Optional Nace Drex decision support; leave the key empty to disable routing.
    nace_api_key: str = ""
    nace_model: str = "drex-latest"
    frontend_base_url: str = "http://localhost:8080"
    expose_auth_action_links: bool = True
    # Local filesystem is for development only; production must use private S3.
    storage_provider: str = "local"
    upload_dir: str = "./data/uploads"
    storage_s3_bucket: str = ""
    storage_s3_region: str = "ap-northeast-1"
    storage_s3_endpoint_url: str = ""
    storage_s3_access_key_id: str = ""
    storage_s3_secret_access_key: str = ""
    # Uploads are scanned before persistence. Disabled only for isolated local development.
    malware_scan_enabled: bool = False
    malware_scanner_host: str = ""
    malware_scanner_port: int = 3310
    malware_scanner_timeout_seconds: float = 30.0
    rate_limit_enabled: bool = False
    rate_limit_fail_closed: bool = True
    api_rate_limit_per_minute: int = Field(default=120, ge=1, le=10000)
    auth_rate_limit_per_minute: int = Field(default=10, ge=1, le=1000)
    registration_rate_limit_per_minute: int = Field(default=5, ge=1, le=1000)
    password_reset_rate_limit_per_minute: int = Field(default=3, ge=1, le=1000)
    rate_limit_redis_timeout_seconds: float = Field(default=1.0, ge=0.1, le=10.0)
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
