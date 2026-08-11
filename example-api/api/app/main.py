import hashlib
import os

import sqlspectre
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine, get_db
from app.models import Merchant, Order, User
from app.schemas import (
    MerchantCreate,
    MerchantOut,
    OrderCreate,
    OrderOut,
    UserCreate,
    UserOut,
)

app = FastAPI(title="sqlspectre example-api")

sqlspectre.configure(
    output=os.path.join(os.path.dirname(__file__), "sqlspectre_output"),
    output_format="csv",
)
sqlspectre.attach(app, engine)



def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


@app.get("/health")
def health():
    return {"ok": True}


# --- auth / users ---


@app.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(409, "email already registered")
    user = User(email=body.email, password_hash=_hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "user not found")
    return user


@app.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.id)).all()


# --- merchants ---


@app.post("/merchants", response_model=MerchantOut, status_code=201)
def create_merchant(body: MerchantCreate, db: Session = Depends(get_db)):
    if not db.get(User, body.owner_id):
        raise HTTPException(404, "owner not found")
    merchant = Merchant(name=body.name, owner_id=body.owner_id)
    db.add(merchant)
    db.commit()
    db.refresh(merchant)
    return merchant


@app.get("/merchants/{merchant_id}", response_model=MerchantOut)
def get_merchant(merchant_id: int, db: Session = Depends(get_db)):
    merchant = db.get(Merchant, merchant_id)
    if not merchant:
        raise HTTPException(404, "merchant not found")
    return merchant


@app.get("/merchants", response_model=list[MerchantOut])
def list_merchants(db: Session = Depends(get_db)):
    return db.scalars(select(Merchant).order_by(Merchant.id)).all()


# --- orders ---


@app.post("/orders", response_model=OrderOut, status_code=201)
def create_order(body: OrderCreate, db: Session = Depends(get_db)):
    if not db.get(Merchant, body.merchant_id):
        raise HTTPException(404, "merchant not found")
    if not db.get(User, body.user_id):
        raise HTTPException(404, "user not found")
    order = Order(
        merchant_id=body.merchant_id,
        user_id=body.user_id,
        amount=body.amount,
        status=body.status,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@app.get("/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "order not found")
    return order


@app.get("/orders", response_model=list[OrderOut])
def list_orders(
    merchant_id: int | None = None,
    user_id: int | None = None,
    db: Session = Depends(get_db),
):
    q = select(Order)
    if merchant_id is not None:
        q = q.where(Order.merchant_id == merchant_id)
    if user_id is not None:
        q = q.where(Order.user_id == user_id)
    return db.scalars(q.order_by(Order.id)).all()


@app.get("/merchants/{merchant_id}/orders", response_model=list[OrderOut])
def list_merchant_orders(merchant_id: int, db: Session = Depends(get_db)):
    if not db.get(Merchant, merchant_id):
        raise HTTPException(404, "merchant not found")
    return db.scalars(
        select(Order).where(Order.merchant_id == merchant_id).order_by(Order.id)
    ).all()


##create an endpoint that will find a user, then find the merchant id, and assemble one dict showing merchant_id, owner_emai from it
@app.get("/user-merchant-info")
def user_merchant_info(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "user not found")
    merchant = db.get(Merchant, user.id)
    if not merchant:
        raise HTTPException(404, "merchant not found")
    return {"merchant_id": merchant.id, "owner_email": user.email}
