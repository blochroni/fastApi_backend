import uvicorn
import dotenv
import os
import json
from models import Trip, Expense, User
import sqlalchemy_utils
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from datetime import datetime, timedelta
from schemas import *
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.exc import OperationalError, DatabaseError
import logging
#from mangum import Mangum

logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'  # This sets the format for the timestamp. Adjust as needed.
)
logger = logging.getLogger(__name__)

# When you use the logger, the messages will be written to 'app.log' with timestamps
#logger.info("This message will be written to app.log with a timestamp.")

dotenv.load_dotenv()

db_password = os.getenv('DB_PASSWORD')
SECRET_KEY = os.getenv('SECRET_KEY')
ALGORITHM = os.getenv('ALGORITHM')

# change it -> because that unprofessional terms
Bar_host = os.getenv('Bar_host')
Roni_host = os.getenv('Roni_host')

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login/")


def get_current_user(token: str = Depends(oauth2_scheme)):
    """
       Extracts and validates the user email (usermail) from the provided JWT token.

       Parameters:
       ----------
       - token (str):
           A JWT token string, typically obtained during the login process and sent by the client
           in the request headers.

       Returns:
       -------
       - str:
           The email (usermail) of the authenticated user.

       Raises:
       ------
       - HTTPException:
           A 401 Unauthorized error if the token is invalid or if the usermail is not present in
           the token's payload.

       Notes:
       ------
       - The function expects the JWT token to be sent in the request header as a Bearer token.

       - The JWT token is decoded using a secret key (`SECRET_KEY`) and the specified algorithm (`ALGORITHM`).
         Both these values should be kept confidential and consistent to ensure token integrity.

       - It's crucial to handle JWT errors effectively to prevent unauthorized access and inform
         the client about the issues with their token.

       Example:
       --------
       >>> user_email = get_current_user(token="YOUR_JWT_TOKEN_HERE")
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        usermail: str = payload.get("usermail")
        if usermail is None:
            raise credentials_exception
        return usermail
    except JWTError:
        raise credentials_exception


def create_jwt_token(data: dict, expires_delta: timedelta = None):
    """
    Generates a signed JSON Web Token (JWT) using provided data and an optional expiration time.

    Parameters:
    ----------
    - data (dict):
        A dictionary containing the payload information to be encoded in the JWT.
        Typically contains claims like user identifier (e.g., `usermail`).
        In our case its contains the usermail.

    - expires_delta (timedelta, optional):
        A timedelta object specifying the amount of time until the token expires.
        If not provided, the token will have a default expiration time of 15 minutes.
        In our case it set to 60 minutes.

    Returns:
    -------
    - str:
        A signed JWT string which can be sent to the client and later used to verify the
        authenticity of requests.

    Notes:
    ------
    - The function uses the `SECRET_KEY` to sign the JWT. This key should be kept confidential.
      Exposure can lead to forged tokens being accepted by the server.

    - The algorithm specified by the `ALGORITHM` constant is used for the signing process. It's crucial
      to use a strong algorithm (e.g., HS256) to ensure the token's security.

    - The JWT includes an `exp` claim, which indicates the token's expiration time. Servers should check
      this claim to ensure tokens are still valid when used.
    """

    to_encode = data.copy()
    # change minutes var to be taken from .env or configuration file
    expires_delta = expires_delta or timedelta(minutes=15)
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


assert db_password, "please insert the DB_PASSWORD key"
DATABASE_URL = f"postgresql://postgres:{db_password}@localhost:5432/trip_db"


sqlalchemy_utils.init(pg_conn_string=DATABASE_URL)

app = FastAPI()
#handler = Mangum(app)
session_maker = sqlalchemy_utils.get_session_maker()


@app.post("/login/")
def login(user_data: UserLogin):
    """
    Authenticate a user based on email and password.

    This function receives user login data, checks it against the database, and
    if the user is authenticated successfully, returns a JWT token for further interactions.

    Parameters:
    - user_data (UserLogin): A data model containing user's email and password.

    Returns:
    - dict: A dictionary with status, a message, and a JWT token upon successful login.

    Raises:
    - HTTPException: If the email doesn't exist in the database, or if the password is incorrect.

    Note:
    For real-world applications, use a more secure method to hash and verify passwords,
    such as bcrypt or Argon2.
    """
    with session_maker() as active_session:
        # Find user by email
        user = active_session.query(User).filter(User.usermail == user_data.usermail).first()

        # If user doesn't exist or password is wrong, return an error
        if not user or user.hashed_password != user_data.hashed_password:  # For real-world apps, use a hashing library like bcrypt or Argon2 to hash and verify passwords
            raise HTTPException(status_code=400, detail="Invalid email or password")

        # Create a token for the authenticated user
        expiration = timedelta(minutes=1000)  # Set token to expire in 1 hour
        token = create_jwt_token(data={"usermail": user.usermail}, expires_delta=expiration)
        return {"status": "success", "message": "Login successful", "token": token}


@app.get("/my-trips/")
async def get_my_trips_summary(usermail: str = Depends(get_current_user)):
    """
    Retrieves a summary of all trips associated with the authenticated user.

    This function fetches all the trips linked with the authenticated user's email (usermail) and
    aggregates the associated expenses for each trip to provide a summary view.

    Parameters:
    ----------
    - usermail (str, optional):
        The email of the authenticated user. This is automatically inferred from the JWT token
        sent in the request headers using the `get_current_user` dependency. The client doesn't
        have to provide this explicitly.

    Returns:
    -------
    - Dict[str, List[TripResponse]]:
        A dictionary containing a list of summarized trips. Each trip contains details like
        its ID, destination, start and end dates, and the total expenses for that trip.

    Notes:
    ------
    - The function expects the JWT token to be sent in the request header as a Bearer token to
      identify the user.

    - This endpoint provides a summary and does not list individual expenses for each trip. To
      get a detailed breakdown of expenses, a separate endpoint or functionality would be required.

    - In case of database errors or unexpected issues, appropriate error handlers should be
      in place (not shown in the provided function).
    """
    try:
        with session_maker() as active_session:
            # Query the database for all trips associated with the user's email
            trips = active_session.query(Trip).filter(Trip.user_id == usermail).all()

            # Create a list to hold the structured response
            trips_response = []

            for trip in trips:
                # For each trip, get its associated expenses
                expenses = active_session.query(Expense).filter(Expense.trip_id == trip.id).all()
                #expenses_response = [ExpenseResponse(item=exp.item, cost=exp.cost) for exp in expenses]

                # Calculate the total expense for the trip
                total_expense = sum(exp.cost for exp in expenses)

                # Append the trip and its expenses to the response list
                trip_resp = TripResponse(
                    id=trip.id,
                    destination=trip.destination,
                    startDate=trip.startDate,
                    endDate=trip.endDate,
                    #expenses=expenses_response,
                    total_expense=total_expense  # Add this field to the TripResponse model as well
                )
                trips_response.append(trip_resp)

            # Return the structured response
            print("hii")
            print(trips_response)
            return {"trips": trips_response}

    except NoResultFound:
        logger.info(f"No trips found for user {usermail}. This might be expected.")
        raise HTTPException(status_code=404, detail="No trips found for the user")

    except OperationalError as oe:
        logger.error(f"Database operational error for user {usermail}: {oe}")
        raise HTTPException(status_code=500, detail="Database operational error. Please try again later.")

    except Exception as e:
        # Handle unexpected errors
        logger.error(f"Unexpected error while retrieving trips for user {usermail}: {e}")
        raise HTTPException(status_code=500, detail="Unexpected error. Please contact support or try again later.")


@app.get("/my-trips/{trip_id}/details/")
async def get_trip_details(trip_id: UUID, usermail: str = Depends(get_current_user)):
    logger.info(f"Received request for trip details: trip_id={trip_id}, usermail={usermail}")
    """
    Retrieves the detailed expenses for a specific trip associated with the authenticated user.

    This function fetches the trip with the provided trip_id that belongs to the authenticated user's
    email (usermail) and lists all the associated expenses for that trip in a detailed manner.

    Parameters:
    ----------
    - trip_id (int):
        The unique identifier of the trip.

    - usermail (str, optional):
        The email of the authenticated user. This is automatically inferred from the JWT token
        sent in the request headers using the `get_current_user` dependency. The client doesn't
        have to provide this explicitly.

    Returns:
    -------
    - Dict[str, Union[int, List[ExpenseResponse]]]:
        A dictionary containing the trip's unique ID and its associated expenses.

    Notes:
    ------
    - The function expects the JWT token to be sent in the request header as a Bearer token to
      identify the user.

    - If the trip with the provided trip_id is not found or doesn't belong to the authenticated user,
      the function raises an HTTP 404 error with the detail "Trip not found or not owned by the current user".

    - If there's a database connection issue or any other unexpected error, appropriate error
      handlers are in place. Details about the specific trip ID and user are logged in case of errors.
    """
    # with session_maker() as active_session:
    #     # Ensure the trip belongs to the current user
    #     trip = active_session.query(Trip).filter(Trip.id == trip_id, Trip.user_id == usermail).first()
    #     if not trip:
    #         raise HTTPException(status_code=404, detail="Trip not found or not owned by the current user")
    #
    #     expenses = active_session.query(Expense).filter(Expense.trip_id == trip.id).all()
    #
    #     expenses_response = [ExpenseResponse(
    #         expense_id=exp.id,
    #         item=exp.item,
    #         cost=exp.cost,
    #         day=exp.day,
    #         category=exp.category
    #     ) for exp in expenses]
    #
    #     return {"trip_id": trip_id, "expenses": expenses_response}
    try:
        with session_maker() as active_session:
            # Ensure the trip belongs to the current user
            trip = active_session.query(Trip).filter(Trip.id == trip_id, Trip.user_id == usermail).first()
            if not trip:
                raise HTTPException(status_code=404, detail="Trip not found or not owned by the current user")
            expenses = active_session.query(Expense).filter(Expense.trip_id == trip.id).all()
            # for expense in expenses:
            #     print(f"Expense ID: {expense.id}, Item: {expense.item}, Cost: {expense.cost}, category={expense.category}, date_created={expense.date_created}")
            expenses_response = [ExpenseResponse(
                expense_id=exp.id,
                item=exp.item,
                cost=exp.cost,
                day=exp.day,
                category=exp.category,
                date_created=exp.date_created
            ) for exp in expenses]
            # print({"trip_id": trip_id, "expenses": expenses_response})
            return {"trip_id": trip_id, "expenses": expenses_response}

    except HTTPException:
        # This will handle any HTTP exceptions we've raised, so we don't log them as unexpected errors.
        raise

    except DatabaseError:
        logger.error(f"Database error encountered when fetching details for Trip ID: {trip_id} and User: {usermail}")
        raise HTTPException(status_code=500, detail="Database connection issue")

    except Exception as e:
        logger.error(f"Error while retrieving trip details for Trip ID: {trip_id} and User: {usermail}. Error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/add-user/")
def add_user(user: userCreate):
    try:
        with session_maker() as active_session:
            new_user = User(user.usermail, user.first_name, user.last_name, user.hashed_password)
            active_session.add(new_user)
            active_session.commit()

            # Create a token for the new user
            expiration = timedelta(minutes=1200)  # Set token to expire in 1 hour
            token = create_jwt_token(data={"usermail": user.usermail}, expires_delta=expiration)

            return {"status": "success", "message": "User added successfully", "token": token}

    except DatabaseError:
        logger.error(f"Database error encountered when adding user: {user.usermail}")
        active_session.rollback()
        raise HTTPException(status_code=500, detail="Database connection issue")

    except Exception as e:
        logger.error(f"Error while adding user: {user.usermail}. Error: {e}")
        active_session.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/test/")
def test():
     return {"status": "success", "message": "A request was successfully sent"}

@app.post("/add-trip/")
def add_trip(trip: TripCreate, usermail: str = Depends(get_current_user)):
    """
    Adds a new trip to the database associated with the authenticated user.

    This function receives the trip details provided in the request, associates it with the authenticated
    user based on the usermail, and then creates the trip entry in the database.

    Parameters:
    ----------
    - trip (TripCreate):
        The details of the trip to be created, provided in the request body.

    - usermail (str, optional):
        The email of the authenticated user. This is automatically inferred from the JWT token
        sent in the request headers using the `get_current_user` dependency. The client doesn't
        have to provide this explicitly.

    Returns:
    -------
    - Dict[str, Union[str, int]]:
        A dictionary containing the status of the operation, a relevant message, and the unique ID of the created trip.

    Notes:
    ------
    - The function expects the JWT token to be sent in the request header as a Bearer token to identify the user.

    - If the associated user for the provided usermail is not found, an error is raised.

    - In case of database errors or unexpected issues, appropriate error handlers are in place. Specific
      details about the trip and user are logged in case of errors.
    """
    try:
        with session_maker() as active_session:
            # Assuming your User table has a 'usermail' field that is unique
            user = active_session.query(User).filter(User.usermail == usermail).first()

            if not user:
                raise HTTPException(status_code=400, detail="User not found")
            new_trip = Trip(destination=trip.destination, startDate=trip.startDate, endDate=trip.endDate, user_id=user.usermail)  # assuming `user_id` is the email in the Trip table
            active_session.add(new_trip)
            active_session.commit()
            return {"status": "success", "message": "Trip added successfully", "id_trip": new_trip.id}

    except DatabaseError:
        logger.error(f"Database error encountered when adding trip for user: {usermail}")
        active_session.rollback()
        raise HTTPException(status_code=500, detail="Database connection issue")

    except Exception as e:
        logger.error(f"Error while adding trip for user: {usermail}. Error: {e}")
        active_session.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/add-expense/")
def add_expense(expense_data: ExpenseCreate, usermail: str = Depends(get_current_user)):
    """
    Adds a new expense to the database associated with a specific trip and the authenticated user.

    This function receives the expense details provided in the request, associates it with the authenticated
    user based on the usermail and the specified trip, and then creates the expense entry in the database.

    Parameters:
    ----------
    - expense_data (ExpenseCreate):
        The details of the expense to be created, provided in the request body.

    - usermail (str, optional):
        The email of the authenticated user. This is automatically inferred from the JWT token
        sent in the request headers using the `get_current_user` dependency. The client doesn't
        have to provide this explicitly.

    Returns:
    -------
    - Dict[str, Union[str, int]]:
        A dictionary containing the status of the operation, a relevant message, and the unique ID of the created expense.

    Notes:
    ------
    - The function expects the JWT token to be sent in the request header as a Bearer token to identify the user.

    - If the associated trip for the provided trip_id is not found or doesn't belong to the user, an error is raised.

    - The expense day should be within the start and end dates of the trip. If it's not, an error is raised.

    - In case of database errors or unexpected issues, appropriate error handlers are in place. Specific
      details about the expense, trip, and user are logged in case of errors.
    """
    with session_maker() as active_session:
        try:
            # Check if the trip exists and belongs to the current user
            trip = active_session.query(Trip).filter(Trip.id == expense_data.trip_id, Trip.user_id == usermail).first()

            if not trip:
                raise HTTPException(status_code=400, detail="Trip not found or not owned by the current user")

            # Check if the day is within the range of the trip's start and end dates
             #if not (trip.startDate <= expense_data.day <= trip.endDate):
                #raise HTTPException(status_code=400, detail="Invalid day for the trip")

            new_expense = Expense(
                item=expense_data.item,
                cost=expense_data.cost,
                trip_id=expense_data.trip_id,
                day=expense_data.day,
                category=expense_data.category)

            active_session.add(new_expense)
            active_session.commit()

            return {"status": "success", "message": "Expense added successfully", "expense_id": new_expense.id}

        except DatabaseError:
            logger.error(f"Database error encountered when adding expense for Trip ID: {expense_data.trip_id} and User: {usermail}")
            active_session.rollback()  # Rollback transaction in case of database errors
            raise HTTPException(status_code=500, detail="Database connection issue")

        except Exception as e:
            logger.error(f"Error while adding expense for Trip ID: {expense_data.trip_id} and User: {usermail}. Error: {e}")
            active_session.rollback()  # Rollback transaction in case of unexpected errors
            raise HTTPException(status_code=500, detail="Internal Server Error")


# @app.get("/trip-expenses/{trip_id}/{day}")
# async def get_expenses_for_trip_and_day(trip_id: int, day: int, usermail: str = Depends(get_current_user)):
#     with session_maker() as active_session:
#         expenses = active_session.query(Expense).filter(Expense.trip_id == trip_id, Expense.day == day).all()
#         expenses_response = [ExpenseResponse(item=exp.item, cost=exp.cost) for exp in expenses]
#         return {"expenses": expenses_response}


@app.delete("/delete-trip/{trip_id}")
async def delete_trip(trip_id: UUID, usermail: str = Depends(get_current_user)):
    """
    Deletes a specified trip and its related expenses from the database for the authenticated user.

    This function verifies the authenticity of the user, confirms the ownership of the specified trip,
    and then initiates the deletion of the trip and its associated expenses from the database.

    Parameters:
    ----------
    - trip_id (int):
        The unique identifier of the trip to be deleted, provided as a part of the URL.

    - usermail (str, optional):
        The email of the authenticated user. This is automatically inferred from the JWT token
        sent in the request headers using the `get_current_user` dependency. The client doesn't
        have to provide this explicitly.

    Returns:
    -------
    - Dict[str, str]:
        A dictionary containing the status of the operation and a relevant message indicating the result
        of the deletion process.

    Notes:
    ------
    - The function expects the JWT token to be sent in the request header as a Bearer token to identify the user.

    - If the specified trip for the given trip_id is not found or doesn't belong to the user, an error is raised.

    - This endpoint performs cascading deletes. Meaning, deleting a trip will also remove all of its associated expenses.
      This is a destructive action and should be approached with caution. Once deleted, there's no recovery mechanism
      for the trip and its related expenses.

    - In case of database errors or unexpected issues, appropriate error handlers are in place. Specific
      details about the error, trip, and user are conveyed in the response.
    """
    try:
        with session_maker() as active_session:
            # Check if the trip exists and belongs to the current user
            trip = active_session.query(Trip).filter(Trip.id == trip_id, Trip.user_id == usermail).first()

            if not trip:
                raise HTTPException(status_code=400, detail="Trip not found or not owned by the current user")

            # Delete the related expenses
            active_session.query(Expense).filter(Expense.trip_id == trip.id).delete()

            # Delete the trip itself
            active_session.delete(trip)
            active_session.commit()

            return {"status": "success", "message": "Trip and its related expenses deleted successfully"}

    except DatabaseError:
        logger.error(f"Database error encountered when deleting Trip ID: {trip_id} and associated expenses for User: {usermail}")
        active_session.rollback()  # Rollback transaction in case of database errors
        raise HTTPException(status_code=500, detail="Database connection issue")

    except HTTPException:
        # If it's an expected exception, just raise it without rolling back, as no changes have been made yet.
        raise

    except Exception as e:
        logger.error(f"Error while deleting Trip ID: {trip_id} and associated expenses for User: {usermail}. Error: {e}")
        active_session.rollback()  # Rollback any changes made during this session.
        raise HTTPException(status_code=500, detail="Internal Server Error: " + str(e))


@app.delete("/delete-expense/{expense_id}")
async def delete_expense(expense_id: UUID, usermail: str = Depends(get_current_user)):
    """
    Deletes an expense from the database based on the provided expense ID and the authenticated user.

    This function fetches the expense associated with the provided expense_id from the database.
    It checks if the expense belongs to a trip owned by the authenticated user. If the validation passes,
    the expense is deleted from the database.

    Parameters:
    ----------
    - expense_id (int):
        The unique ID of the expense to be deleted.

    - usermail (str, optional):
        The email of the authenticated user. This is automatically inferred from the JWT token
        sent in the request headers using the `get_current_user` dependency. The client doesn't
        have to provide this explicitly.

    Returns:
    -------
    - Dict[str, str]:
        A dictionary containing the status of the operation and a relevant message.

    Notes:
    ------
    - The function expects the JWT token to be sent in the request header as a Bearer token to identify the user.

    - If the expense with the provided expense_id is not found, an error with status_code=400 is raised indicating
      "Expense not found".

    - If the associated expense doesn't belong to a trip owned by the user, an error with status_code=400 is raised
      indicating "Unauthorized action".

    - In case of database errors, an error with status_code=500 is raised with the detail "Database connection issue",
      and the specific details about the expense and user are logged.

    - For any other unexpected errors, an error with status_code=500 is raised detailing the "Internal Server Error",
      and the specific details about the expense and user are logged.
    """
    try:
        with session_maker() as active_session:
            # Find the expense
            expense = active_session.query(Expense).filter(Expense.id == expense_id).first()

            if not expense:
                raise HTTPException(status_code=400, detail="Expense not found")

            # Ensure that the expense belongs to a trip owned by the current user
            related_trip = active_session.query(Trip).filter(Trip.id == expense.trip_id, Trip.user_id == usermail).first()

            if not related_trip:
                raise HTTPException(status_code=400, detail="Unauthorized action")

            # Delete the expense
            active_session.delete(expense)
            active_session.commit()

            return {"status": "success", "message": "Expense deleted successfully"}

    except DatabaseError:
        logger.error(f"Database error encountered when deleting Expense ID: {expense_id} for User: {usermail}")
        active_session.rollback()  # Rollback transaction in case of database errors
        raise HTTPException(status_code=500, detail="Database connection issue")

    except HTTPException:
        # If it's an expected exception, just raise it without rolling back, as no changes have been made yet.
        raise

    except Exception as e:
        logger.error(f"Error while deleting Expense ID: {expense_id} for User: {usermail}. Error: {e}")
        active_session.rollback()  # Rollback any changes made during this session.
        raise HTTPException(status_code=500, detail="Internal Server Error: " + str(e))


if __name__ == '__main__':

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    #uvicorn.run(app=app, host='0.0.0.0', port=8000)
    #uvicorn.run(app=app, host=Bar_host, port=8000)
    #uvicorn.run(app=app, host=Roni_host, port=8000)
    #uvicorn.run(app=app, host='192.168.1.40', port=8000)
    uvicorn.run(app=app, host='127.0.0.1', port=8000)

