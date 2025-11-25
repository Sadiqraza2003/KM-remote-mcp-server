# models/Expense.py
from sqlalchemy import Column, Integer, String, Date, Float, ForeignKey
from sqlalchemy.orm import relationship
from db.database import Base
from models.User import User

class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Float, nullable=False)
    date = Column(Date, nullable=False)
    category = Column(String(255), nullable=False)
    subcategory = Column(String(255), nullable=True)
    note = Column(String(500), nullable=True)

    # NEW COLUMN
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)

    # Relationship (optional but useful)
    user = relationship("User")
