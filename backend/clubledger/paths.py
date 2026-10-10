# In plain English: Finds the frontend and migration files in both local and installed copies.
"""Locate the frontend and migrations without depending on the working directory.

These folders are installed as resource packages, so wheels and editable installs
use the same paths. They contain assets, not another web server.
"""

from pathlib import Path
import frontend
import database

FRONTEND_DIR = Path(frontend.__file__).resolve().parent
TEMPLATES_DIR = FRONTEND_DIR / "templates"
STATIC_DIR = FRONTEND_DIR / "static"
MIGRATIONS_DIR = Path(database.__file__).resolve().parent / "migrations"
