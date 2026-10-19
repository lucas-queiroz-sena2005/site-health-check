import logging
from zoneinfo import ZoneInfo
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("config")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")
    
    # Default window to consider an IP as a Ghost if it was active previously
    # Format: <int>[s|m|h|d], e.g., "7d", "24h"
    default_ghost_window: str = "7d"
    
    # Domain configuration (automatically loads DOMAIN_NAME from .env)
    domain_name: str = Field(
        default="localhost",
        validation_alias=AliasChoices("domain_name", "DOMAIN_NAME"),
    )
    enable_ssl: bool = Field(
        default=False,
        validation_alias=AliasChoices("enable_ssl", "ENABLE_SSL"),
    )
    http_port: int = Field(
        default=80,
        validation_alias=AliasChoices("http_port", "HTTP_PORT"),
    )
    https_port: int = Field(
        default=443,
        validation_alias=AliasChoices("https_port", "HTTPS_PORT"),
    )

    @property
    def base_url(self) -> str:
        d = self.domain_name.strip()
        if d.startswith("http://") or d.startswith("https://"):
            return d.rstrip("/")
        
        scheme = "https" if self.enable_ssl else "http"
        port = self.https_port if self.enable_ssl else self.http_port
        
        if ":" in d:
            return f"{scheme}://{d}".rstrip("/")
        
        if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
            return f"{scheme}://{d}"
            
        return f"{scheme}://{d}:{port}"

    @property
    def app_base_url(self) -> str:
        return self.base_url


    # Timezone for scheduled cron evaluations (e.g., "America/Sao_Paulo", "UTC")
    # Supports TIMEZONE, TZ, APP_TIMEZONE
    timezone: str = Field(
        default="UTC",
        validation_alias=AliasChoices("timezone", "TIMEZONE", "tz", "TZ", "app_timezone", "APP_TIMEZONE"),
    )

    def get_tz(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.timezone)
        except Exception as e:
            logger.warning("Invalid timezone '%s', falling back to UTC: %s", self.timezone, e)
            return ZoneInfo("UTC")

settings = Settings()

