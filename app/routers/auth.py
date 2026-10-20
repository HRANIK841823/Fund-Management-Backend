from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas import ChangePasswordIn, LoginRequest, MessageOut, TokenOut, UserOut
from app.security import DUMMY_HASH, create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

INVALID_LOGIN = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Incorrect email/username or password.",
    headers={"WWW-Authenticate": "Bearer"},
)


@router.post("/login", response_model=TokenOut)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    identifier = data.identifier.strip().lower()
    column = User.email if "@" in identifier else User.username
    user = db.scalar(select(User).where(column == identifier))

    if user is None:
        verify_password(data.password, DUMMY_HASH)  # keep timing similar
        raise INVALID_LOGIN
    if not verify_password(data.password, user.password_hash):
        raise INVALID_LOGIN
    if not user.is_active or user.deleted_at is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been disabled.")

    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/change-password", response_model=MessageOut)
def change_password(
    data: ChangePasswordIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect.")
    if data.current_password == data.new_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "New password must be different.")
    user.password_hash = hash_password(data.new_password)
    db.commit()
    return MessageOut(message="Password updated.")
