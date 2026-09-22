from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")
    
    # Default window to consider an IP as a Ghost if it was active previously
    # Format: <int>[s|m|h|d], e.g., "7d", "24h"
    default_ghost_window: str = "7d"

settings = Settings()
