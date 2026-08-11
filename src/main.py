import logging
from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session
from . import schemas, crud, models, security
from .database import get_db, create_db_and_tables # Assuming create_db_and_tables is here
from .config import settings

# Configure logging
logging.basicConfig(level=settings.LOG_LEVEL.upper(), format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

# This would ideally be run on startup, e.g., in a separate script or with Alembic
# @app.on_event("startup")
# def on_startup():
#     create_db_and_tables()

@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    logger.warning(f"Validation error: {exc.errors()} - Request path: {request.url.path}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Invalid input provided. Please check your data.", "errors": exc.errors()}
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code >= 400:
        logger.error(f"HTTP Exception: {exc.status_code} - {exc.detail} - Request path: {request.url.path}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception: {exc} - Request path: {request.url.path}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred. Please try again later."}
    )

@app.post("/login", response_model=schemas.Token)
async def login_for_access_token(form_data: security.OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    owner = security.authenticate_user(db, form_data.username, form_data.password)
    if not owner:
        logger.warning(f"Failed login attempt for username: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = security.create_access_token(data={"sub": owner.email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/bookings/", response_model=schemas.Booking)
async def create_booking(booking: schemas.BookingCreate, db: Session = Depends(get_db), current_owner: models.Owner = Depends(security.get_current_owner)):
    try:
        # Basic input validation for customer_name and customer_email
        if not booking.customer_name or len(booking.customer_name) > 100 or any(char in booking.customer_name for char in ['<', '>', '&', '"', "'"]):
            logger.warning(f"Potential XSS/input overflow attempt in customer_name: {booking.customer_name}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid customer name format.")
        
        # Verify that the service belongs to the current owner (IDOR protection)
        service = db.query(models.Service).filter(
            models.Service.id == booking.service_id,
            models.Service.owner_id == current_owner.id
        ).first()
        if not service:
            logger.warning(f"Owner {current_owner.id} attempted to book service {booking.service_id} not owned by them.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found or not owned by you.")

        db_booking = crud.create_booking(db=db, booking=booking, owner_id=current_owner.id)
        logger.info(f"Booking created by owner {current_owner.id} for service {booking.service_id}.")
        return db_booking
    except ValidationError as e:
        logger.warning(f"Booking data validation failed: {e.errors()}")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid booking data.")
    except HTTPException as e:
        raise e # Re-raise controlled HTTP exceptions
    except Exception as e:
        logger.exception(f"Error creating booking: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error.")

# Example of a protected endpoint (dashboard, profile update, etc.)
@app.get("/owner/me", response_model=schemas.Owner)
async def read_current_owner(current_owner: models.Owner = Depends(security.get_current_owner)):
    return current_owner