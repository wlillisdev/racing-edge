"""
config.py — centralised configuration loader.

Reads from the .env file at the project root (one level above src/).
All other modules should import get_config() rather than touching os.environ
directly, so that the single source-of-truth is enforced and missing keys
surface immediately with a clear KeyError.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Bootstrap: load .env once at import time.
# ---------------------------------------------------------------------------
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path)


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------

@dataclass
class Config:
    # Racing API Pro
    racing_api_key: str
    racing_api_base: str

    # MySQL database
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_pass: str

    # Email / SMTP
    email_sender: str
    email_password: str
    email_recipient: str
    smtp_host: str
    smtp_port: int

    # Project meta
    project_dir: str
    model_version: str
    regions: str


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_config() -> Config:
    """
    Build and return a Config instance from environment variables.

    Raises KeyError for any mandatory variable that is absent from the
    environment (i.e. not set in .env and not exported by the shell).
    Optional variables fall back to documented defaults.
    """
    return Config(
        # API — mandatory
        racing_api_key=os.environ["RACING_API_KEY"],
        racing_api_base=os.environ.get(
            "RACING_API_BASE", "https://api.theracingapi.com/v1"
        ),
        # Database — all mandatory
        db_host=os.environ["DB_HOST"],
        db_port=int(os.environ.get("DB_PORT", "3306")),
        db_name=os.environ["DB_NAME"],
        db_user=os.environ["DB_USER"],
        db_pass=os.environ["DB_PASS"],
        # Email — mandatory
        email_sender=os.environ["EMAIL_SENDER"],
        email_password=os.environ["EMAIL_PASSWORD"],
        email_recipient=os.environ["EMAIL_RECIPIENT"],
        smtp_host=os.environ.get("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=int(os.environ.get("SMTP_PORT", "587")),
        # Project — optional with sensible defaults
        project_dir=os.environ.get(
            "PROJECT_DIR", str(Path(__file__).parent.parent)
        ),
        model_version=os.environ.get("MODEL_VERSION", "v3"),
        regions=os.environ.get("REGIONS", "gb,ire"),
    )
