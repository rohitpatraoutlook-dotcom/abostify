import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(parents=True, exist_ok=True)


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    if not SECRET_KEY:
        if (
            os.environ.get("RENDER")
            or os.environ.get("FLASK_ENV") == "production"
        ):
            raise RuntimeError(
                "SECRET_KEY must be configured in production."
            )
        SECRET_KEY = "local-development-only-change-me"

    DATABASE_URL = os.environ.get("DATABASE_URL")

    if DATABASE_URL:
        if DATABASE_URL.startswith("postgres://"):
            DATABASE_URL = DATABASE_URL.replace(
                "postgres://",
                "postgresql+psycopg://",
                1
            )
        elif DATABASE_URL.startswith("postgresql://"):
            DATABASE_URL = DATABASE_URL.replace(
                "postgresql://",
                "postgresql+psycopg://",
                1
            )

        SQLALCHEMY_DATABASE_URI = DATABASE_URL
    else:
        SQLALCHEMY_DATABASE_URI = (
            "sqlite:///" + str(INSTANCE_DIR / "abostify.db")
        )

    SQLALCHEMY_TRACK_MODIFICATIONS = False
