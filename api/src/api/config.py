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
    
    # Base URL for frontend dashboard links in alerts
    app_base_url: str = "http://localhost:8080"

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

