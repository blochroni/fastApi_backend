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
import firebase_admin
from firebase_admin import credentials, auth

cred = credentials.Certificate("travelsmartfastapi-firebase-adminsdk.json")
firebase_admin.initialize_app(cred)

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

dotenv.load_dotenv()

db_password = os.getenv('DB_PASSWORD')
SECRET_KEY = os.getenv('SECRET_KEY')
ALGORITHM = os.getenv('ALGORITHM')
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = os.getenv("SMTP_PORT")
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

# change it -> because that unprofessional terms
Bar_host = os.getenv('Bar_host')
Roni_host = os.getenv('Roni_host')


def send_verification_email(receiver_email, verification_link):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = receiver_email
    msg['Subject'] = "Verify Your Email"
    body = f"Please verify your email by clicking on this link: <a href='{verification_link}'>Verify Email</a>"
    msg.attach(MIMEText(body, 'html'))

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, receiver_email, msg.as_string())
        server.quit()
        print("Email sent successfully")
    except Exception as e:
        print(f"Failed to send email: {e}")



logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'  # This sets the format for the timestamp. Adjust as needed.
)
logger = logging.getLogger(__name__)

# When you use the logger, the messages will be written to 'app.log' with timestamps
#logger.info("This message will be written to app.log with a timestamp.")



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

app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
session_maker = sqlalchemy_utils.get_session_maker()

@app.post("/login/")
def login(user_data: UserLogin):
    """
    Authenticate a user based on their email and password, and verify their email status via Firebase.

    This endpoint:
    - Verifies user credentials against the database.
    - Checks if the user's email is verified with Firebase.
    - Updates the local database with the email verification status.
    - Generates and returns a JWT token for authenticated sessions.

    Parameters:
    - user_data (UserLogin): A data model containing the user's email (usermail) and password.

    Response:
    - On successful authentication and email verification, returns a success status, a message, and a JWT token.
    - Returns an HTTP 400 error if authentication fails or the email is not verified.

    Raises:
    - HTTPException: With status code 400 for invalid credentials or unverified email.

    Note:
    - The JWT token expires after a predefined duration (e.g., 1000 minutes).
    """
    with session_maker() as active_session:
        user = active_session.query(User).filter(User.usermail == user_data.usermail).first()

        if not user or user.hashed_password != user_data.hashed_password:
            raise HTTPException(status_code=400, detail="Invalid email or password")

        # Check the email verification status with Firebase
        firebase_user = auth.get_user_by_email(user_data.usermail)
        if not firebase_user.email_verified:
            raise HTTPException(status_code=400, detail="Email not verified")

        # Update is_email_verified in your database
        if not user.is_email_verified:
            user.is_email_verified = True
            active_session.commit()

        # Create a token for the authenticated user
        expiration = timedelta(minutes=1000)
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

                # Calculate the total expense for the trip
                total_expense = sum(exp.cost for exp in expenses)

                # Append the trip and its expenses to the response list
                trip_resp = TripResponse(
                    id=trip.id,
                    destination=trip.destination,
                    startDate=trip.startDate,
                    endDate=trip.endDate,
                    total_expense=total_expense,  # Add this field to the TripResponse model as well
                    budget=trip.budget
                )
                trips_response.append(trip_resp)

            # Return the structured response
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
    try:
        with session_maker() as active_session:
            # Ensure the trip belongs to the current user
            trip = active_session.query(Trip).filter(Trip.id == trip_id, Trip.user_id == usermail).first()
            if not trip:
                raise HTTPException(status_code=404, detail="Trip not found or not owned by the current user")
            expenses = active_session.query(Expense).filter(Expense.trip_id == trip.id).all()
            expenses_response = [ExpenseResponse(
                expense_id=exp.id,
                item=exp.item,
                cost=exp.cost,
                day=exp.day,
                category=exp.category,
                date_created=exp.date_created
            ) for exp in expenses]
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
    with session_maker() as active_session:
        existing_user = active_session.query(User).filter(User.usermail == user.usermail).first()

        # Check if user already exists
        if existing_user:
            if not existing_user.is_email_verified:
                # User exists but hasn't verified their email, resend the verification link
                try:
                    firebase_verification_link = auth.generate_email_verification_link(user.usermail)
                    send_verification_email(user.usermail, firebase_verification_link)
                    return {"status": "success", "message": "User already registered but not verified. Verification email resent."}
                except Exception as e:
                    logger.error(f"Failed to resend verification email to: {user.usermail}. Error: {e}")
                    raise HTTPException(status_code=400, detail="Failed to resend verification email")
            else:
                # User exists and is verified, should not register again
                raise HTTPException(status_code=400, detail="Email already registered and verified")

        try:
            # Create Firebase user
            firebase_user = auth.create_user(
                email=user.usermail,
                email_verified=False,
                password=user.hashed_password,
                display_name=f"{user.first_name} {user.last_name}"
            )

            # Generate Firebase email verification link
            firebase_verification_link = auth.generate_email_verification_link(user.usermail)

            # Send the Firebase verification link via email
            send_verification_email(user.usermail, firebase_verification_link)

            # Add user to your database (without email verification)
            new_user = User(user.usermail, user.first_name, user.last_name, user.hashed_password, is_email_verified=False)
            active_session.add(new_user)
            active_session.commit()

            return {"status": "success", "message": "User added successfully, please verify your email"}

        except Exception as e:
            print(e)
            raise HTTPException(status_code=400, detail="Error in user registration")
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
            new_trip = Trip(destination=trip.destination, startDate=trip.startDate, endDate=trip.endDate, user_id=user.usermail, budget=trip.budget)  # assuming `user_id` is the email in the Trip table
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


@app.put("/update-trip/{trip_id}")
def update_trip(trip_id: UUID, trip_update: TripUpdate, usermail: str = Depends(get_current_user)):
    """
    Updates an existing trip with new details.

    Parameters:
    ----------
    trip_id (UUID): The unique identifier of the trip to be updated.
    trip_update (TripUpdate): The updated trip details.
    usermail (str): The email of the authenticated user.

    Returns:
    -------
    A dictionary with the operation status and a message.
    """
    try:
        with session_maker() as active_session:
            # Fetch the existing trip
            trip = active_session.query(Trip).filter(Trip.id == trip_id, Trip.user_id == usermail).first()

            if not trip:
                raise HTTPException(status_code=404, detail="Trip not found")

            # Update fields if they are provided
            if trip_update.destination is not None:
                trip.destination = trip_update.destination
            if trip_update.startDate is not None:
                trip.startDate = trip_update.startDate
            if trip_update.endDate is not None:
                trip.endDate = trip_update.endDate
            if trip_update.budget is not None:
                trip.budget = trip_update.budget

            active_session.commit()
            return {"status": "success", "message": "Trip updated successfully"}

    except Exception as e:
        logger.error(f"Error while updating trip for user: {usermail}. Error: {e}")
        active_session.rollback()
        raise HTTPException(status_code=500, detail="An error occurred during the update.")


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