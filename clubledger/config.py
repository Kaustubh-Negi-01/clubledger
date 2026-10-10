"""Configuration management for ClubLedger."""

import os
import secrets
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    env: str
    db_path: str
    host: str
    port: int
    sim_secret: str


def get_env() -> str:
    env = os.environ.get("CLUBLEDGER_ENV", "dev").lower()
    if env not in {"dev", "test", "prod"}:
        raise ValueError(f"Invalid CLUBLEDGER_ENV: {env}. Must be one of 'dev', 'test', 'prod'.")
    return env


def get_db_path() -> str:
    return os.environ.get("CLUBLEDGER_DB_PATH", "data/clubledger.db")


def get_sim_secret() -> str:
    env = get_env()
    secret = os.environ.get("CLUBLEDGER_SIM_SECRET")
    if secret:
        return secret

    if env == "prod":
        raise ValueError("CLUBLEDGER_SIM_SECRET must be set in prod environment.")

    # In dev or test, load from or generate into data/.sim_secret
    secret_path = Path("data/.sim_secret")
    if secret_path.exists():
        return secret_path.read_text(encoding="utf-8").strip()

    generated = secrets.token_hex(32)
    try:
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        secret_path.write_text(generated, encoding="utf-8")
    except OSError:
        pass
    return generated


def validate_server_binding(host: str, env: str) -> None:
    """Validate binding rules per CONTRACT G10."""
    if env == "dev":
        loopback_hosts = {"127.0.0.1", "localhost", "::1"}
        if host not in loopback_hosts:
            raise ValueError(f"In 'dev' environment, server refuses to bind to non-loopback host: {host}")


def get_config() -> Config:
    env = get_env()
    host = os.environ.get("CLUBLEDGER_HOST", "127.0.0.1")
    port = int(os.environ.get("CLUBLEDGER_PORT", "8000"))
    validate_server_binding(host, env)
    return Config(
        env=env,
        db_path=get_db_path(),
        host=host,
        port=port,
        sim_secret=get_sim_secret(),
    )
