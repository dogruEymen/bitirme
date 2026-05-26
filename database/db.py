from sqlalchemy.orm import declarative_base

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal, engine


db_url = settings.DATABASE_URL
Base = declarative_base()
