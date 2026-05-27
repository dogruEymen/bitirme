from sqlalchemy import Column, Integer, String
from datetime import datetime
from database.db import Base
from .mixins import TimeMixins

class User(TimeMixins, Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True)
    username      = Column(String, index=True, unique=True, nullable=False)
    email         = Column(String, index=True, unique=True, nullable=False)
    password_hash = Column(String, nullable=True)
