from dataclasses import Field
from uuid import UUID
from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional, List


class TripCreate(BaseModel):
    destination: str
    startDate: date
    endDate: Optional[date] = None
    budget: Optional[float] = None

class TripUpdate(BaseModel):
    destination: Optional[str] = None
    startDate: Optional[date] = None
    endDate: Optional[date] = None
    budget: Optional[float] = None


class userCreate(BaseModel):
    usermail: str
    first_name: str
    last_name: str
    hashed_password: str


class UserLogin(BaseModel):
    usermail: str
    hashed_password: str


class ExpenseCreate(BaseModel):
    item: str
    cost: float
    trip_id: UUID
    day: int
    category: str
    #date_created: datetime = Field(default_factory=datetime.utcnow)


class ExpenseResponse(BaseModel):
    expense_id: UUID
    item: str
    cost: float
    day: int
    category: str
    date_created: datetime


class TripResponse(BaseModel):
    id: UUID
    destination: str
    startDate: date
    endDate: Optional[date] = None
    #expenses: List[ExpenseResponse]
    total_expense: float
    budget: Optional[float] = None