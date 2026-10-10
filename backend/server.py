"""Vercel entry point. The database is migrated before deployment, never on requests."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clubledger.main import app
