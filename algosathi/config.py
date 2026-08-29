from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from algosathi.core.enums import Mode

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.yaml"


class StrategyConfig(BaseModel):
    name: str = "sma_crossover"
    fast_period: int = 9
    slow_period: int = 21
    ma_type: str = "sma"


class RiskConfig(BaseModel):
    order_quantity: int = 1
    max_daily_loss: float = 5000.0
    max_open_positions: int = 1


class PaperConfig(BaseModel):
    starting_cash: float = 100_000.0


class YamlConfig(BaseModel):
    mode: Mode = Mode.PAPER
    symbol: str = "INFY"
    exchange: str = "NSE_EQ"
    strategy: StrategyConfig = StrategyConfig()
    risk: RiskConfig = RiskConfig()
    paper: PaperConfig = PaperConfig()
    polling_interval_seconds: int = 60
    candle_interval_minutes: int = 5


def load_yaml_config(path: Path = DEFAULT_SETTINGS_PATH) -> YamlConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return YamlConfig.model_validate(raw)


class Secrets(BaseSettings):
    """Secrets and safety gates loaded from .env (never from settings.yaml)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    upstox_api_key: str = ""
    upstox_api_secret: str = ""
    upstox_redirect_uri: str = "https://127.0.0.1/callback"
    live_trading_confirmed: bool = False

    # Optional: syncs each fill to Supabase for the online dashboard. Bot runs fine without
    # these (paper mode + local SQLite only).
    supabase_url: str = ""
    supabase_service_key: str = ""


class Settings:
    """Combined view of settings.yaml (strategy/risk/mode) + .env (secrets/gates)."""

    def __init__(self, yaml_config: YamlConfig | None = None, secrets: Secrets | None = None):
        self.yaml = yaml_config or load_yaml_config()
        self.secrets = secrets or Secrets()

    @property
    def mode(self) -> Mode:
        return self.yaml.mode

    def require_live_trading_authorized(self) -> None:
        if self.mode == Mode.LIVE and not self.secrets.live_trading_confirmed:
            raise RuntimeError(
                "mode is 'live' in config/settings.yaml but LIVE_TRADING_CONFIRMED is not "
                "'true' in .env. Both must agree before AlgoSathi will place real orders."
            )


def get_settings() -> Settings:
    return Settings()
