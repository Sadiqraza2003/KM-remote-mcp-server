# models/User.py
import uuid
from sqlalchemy import Column, String, Boolean, DateTime, func
from sqlalchemy.dialects.mysql import CHAR
from db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(
        CHAR(36),                       # UUID stored as CHAR
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    email = Column(String(255), unique=True, nullable=False)
    full_name = Column(String(255), nullable=True)
    hashed_password = Column(String(255), nullable=True)
    role = Column(String(50), nullable=False, server_default="user")
    is_approved = Column(Boolean, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
