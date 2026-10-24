from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, overridable via environment variables (FOODIE_ prefix)."""

    model_config = SettingsConfigDict(
        env_prefix="FOODIE_", env_file=".env", extra="ignore", case_sensitive=False
    )

    data_dir: Path = Path("/data")
    db_filename: str = "foodie.db"
    echo_sql: bool = False

    # Recipe ingestion
    seed_on_first_run: bool = True
    # Only sites whose robots.txt and terms permit automated crawling belong here.
    # allrecipes.com is deliberately excluded: it serves 403 to non-browser clients
    # and its terms prohibit scraping and data mining.
    scrape_sites: list[str] = [
        "https://www.bbcgoodfood.com",
    ]
    scrape_max_recipes: int = 500
    scrape_delay_seconds: float = 1.5
    scrape_timeout_seconds: float = 20.0
    scrape_user_agent: str = "FoodieBot/0.1 (self-hosted personal recipe index)"
    scrape_respect_robots: bool = True

    # Inventory behaviour
    expiry_critical_days: int = 2
    expiry_soon_days: int = 5

    # Barcode scanning
    openfoodfacts_url: str = "https://world.openfoodfacts.org"
    barcode_lookup_enabled: bool = True
    barcode_timeout_seconds: float = 8.0

    # Phase 3 placeholders
    llm_base_url: str = "http://localhost:8080/v1"
    llm_model: str = "qwen3"
    searxng_url: str = "http://localhost:8888"

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_filename

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    @property
    def http_cache_dir(self) -> Path:
        return self.data_dir / "http_cache"


settings = Settings()
