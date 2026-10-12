from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase

from .config import Settings


class Base(DeclarativeBase):
    """Declarative metadata shared by the application and Alembic."""


def create_engine_from_settings(settings: Settings) -> Engine:
    """Create a lazy SQLAlchemy engine without opening a database connection."""
    return create_engine(settings.database_url)
