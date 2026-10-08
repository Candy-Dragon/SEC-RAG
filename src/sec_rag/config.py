"""Application settings loaded from environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    model_provider: str = "openai"
    model_name: str = "deepseek-v4-flash"
    model_api_key: str = ""
    model_base_url: str = "https://api.deepseek.com"
    model_temperature: float = 0.0
    model_timeout_seconds: float = 120.0
    model_max_retries: int = 2
    model_max_output_tokens: int = 1024

    storage_root: str = "storage"
    knowledge_base_root: str = ""
    experiment_scope_path: str = "configs/experiment_scope.json"

    @property
    def root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @property
    def storage_path(self) -> Path:
        return self.root / self.storage_root

    @property
    def datasets_raw(self) -> Path:
        return self.storage_path / "datasets" / "raw"

    @property
    def datasets_processed(self) -> Path:
        return self.storage_path / "datasets" / "processed"

    @property
    def knowledge_documents(self) -> Path:
        return self.knowledge_path / "documents"

    @property
    def knowledge_path(self) -> Path:
        return self.root / self.knowledge_base_root if self.knowledge_base_root else self.storage_path / "knowledge_base"

    def processed_for(self, dataset_key: str) -> Path:
        """Per-dataset output root, e.g. processed/cmedqa2/."""
        return self.datasets_processed / dataset_key


settings = Settings()
