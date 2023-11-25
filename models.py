import random
import uuid
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, Date, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID


Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    #id = Column(Integer, primary_key=True, index=True)
    usermail = Column(String, unique=True, primary_key=True, index=True)
    first_name = Column(String, index=True)
    last_name = Column(String, index=True)
    hashed_password = Column(String)

    def __init__(self, usermail, first_name, last_name, hashed_password):
        Base.__init__(self)
        # if id is None:
        #     id = random.randint(1, 1000)
        # self.id = id
        self.usermail = usermail
        self.first_name = first_name
        self.last_name = last_name
        self.hashed_password = hashed_password

class Trip(Base):
    __tablename__ = "trips"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    #id = Column(Integer, primary_key=True, index=True)
    destination = Column(String, index=True)
    startDate = Column(DateTime)
    endDate = Column(DateTime, nullable=True)
    user_id = Column(String, ForeignKey(f"{User.__tablename__}.usermail"))

    # Constructor
    def __init__(self, destination, startDate, endDate, user_id, id = None):
        Base.__init__(self)
        #if id is None:
            #id = random.randint(1, 1000)
        #self.id = id
        self.destination = destination,
        self.startDate = startDate
        self.endDate = endDate
        self.user_id = user_id

class Expense(Base):
    __tablename__ = "expenses"
    #id = Column(Integer, primary_key=True, index=True)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    item = Column(String, index=True)
    cost = Column(Float)
    trip_id = Column(UUID(as_uuid=True), ForeignKey(f"{Trip.__tablename__}.id"))
    day = Column(Integer, nullable=False)
    category = Column(String, nullable=False)
    date_created = Column(DateTime, default=datetime.utcnow)

    def __init__(self, item, cost, trip_id, day, category, id=None):
        Base.__init__(self)
        #if id is None:
            #id = random.randint(1, 1000)
        #self.id = id
        self.item = item
        self.cost = cost
        self.trip_id = trip_id
        self.day = day
        self.category = category