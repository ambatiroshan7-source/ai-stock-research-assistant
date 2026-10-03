"""Load application settings without embedding credentials."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name('.env'))


@dataclass(frozen=True)
class Settings:
    region: str
    profile: str | None
    model_id: str

    @classmethod
    def from_env(cls) -> 'Settings':
        return cls(
            region=os.getenv('AWS_REGION', 'us-east-1'),
            profile=os.getenv('AWS_PROFILE') or None,
            model_id=os.getenv('BEDROCK_MODEL_ID', '').strip(),
        )
