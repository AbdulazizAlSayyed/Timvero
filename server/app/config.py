import os
from pathlib import Path

# Allow override from environment
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # Default to a local sqlite file next to the server folder
    default_db_path = (Path(__file__).resolve().parents[1] / "tempo_tracker.db").resolve()
    DATABASE_URL = f"sqlite:///{default_db_path.as_posix()}"

JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_ME_SECRET")
JWT_ALG = "HS256"
ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "720"))

ROLE_HR = "HR"
ROLE_DATA_ENTRY = "DataEntry"
ROLE_ADMIN = "Admin"
