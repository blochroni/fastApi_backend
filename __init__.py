from sqlalchemy import create_engine
import models

DATABASE_URL = "postgresql://postgres:LIdor123@localhost:5432/trip_db"
engine = create_engine(DATABASE_URL)

models.Base.metadata.create_all(bind=engine)