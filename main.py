from fastapi import FastAPI, HTTPException, Query, Depends, Header
from pydantic import BaseModel, Field
from typing import Literal
import os
import secrets
import time
from dotenv import load_dotenv

from database import (
    create_table,
    add_transaction,
    get_transactions,
    get_balance,
    update_transaction,
    delete_transaction,
    create_link_code,
    link_vk_account,
    get_user_id_by_vk
)

load_dotenv()

API_SECRET_KEY = os.getenv("API_SECRET_KEY")

if not API_SECRET_KEY:
    raise RuntimeError("API_SECRET_KEY не найден")

app = FastAPI()

create_table()


def verify_api_key(x_api_key: str = Header(...)):
    if not secrets.compare_digest(x_api_key, API_SECRET_KEY):
        raise HTTPException(
            status_code=401,
            detail="Неверный API-ключ"
        )


class TransactionCreate(BaseModel):
    type: Literal["expense", "income"]
    amount: float = Field(gt=0)
    category: str = Field(min_length=1)


class TransactionUpdate(BaseModel):
    type: Literal["expense", "income"]
    amount: float = Field(gt=0)
    category: str = Field(min_length=1)


class VKLinkRequest(BaseModel):
    code: str = Field(min_length=1)
    vk_id: int = Field(gt=0)


@app.get("/")
def home():
    return {"message": "Financial Tracker API!"}


# Финансовые операции

@app.get("/transactions", dependencies=[Depends(verify_api_key)])
def get_transactions_api(
    user_id: int = Query(gt=0),
    transaction_type: Literal["expense", "income"] | None = None
):
    transactions = get_transactions(user_id, transaction_type)

    return {"transactions": transactions}


@app.get("/balance", dependencies=[Depends(verify_api_key)])
def get_balance_api(user_id: int = Query(gt=0)):
    return get_balance(user_id)


@app.post("/transactions", dependencies=[Depends(verify_api_key)])
def add_transaction_api(
    transaction: TransactionCreate,
    user_id: int = Query(gt=0)
):
    transaction_id = add_transaction(
        transaction.type,
        transaction.amount,
        transaction.category,
        user_id
    )

    return {
        "message": "Операция добавлена",
        "id": transaction_id,
        "user_id": user_id
    }


@app.put("/transactions/{transaction_id}", dependencies=[Depends(verify_api_key)])
def update_transaction_api(
    transaction_id: int,
    transaction: TransactionUpdate,
    user_id: int = Query(gt=0)
):
    updated = update_transaction(
        transaction_id,
        user_id,
        transaction.type,
        transaction.amount,
        transaction.category
    )

    if not updated:
        raise HTTPException(
            status_code=404,
            detail="Операция не найдена"
        )

    return {"message": "Операция обновлена"}


@app.delete("/transactions/{transaction_id}", dependencies=[Depends(verify_api_key)])
def delete_transaction_api(
    transaction_id: int,
    user_id: int = Query(gt=0)
):
    transaction = delete_transaction(transaction_id, user_id)

    if transaction is None:
        raise HTTPException(
            status_code=404,
            detail="Операция не найдена"
        )

    return {
        "message": "Операция удалена",
        "transaction": transaction
    }


# Привязка VK-аккаунта

@app.post("/link-code", dependencies=[Depends(verify_api_key)])
def create_link_code_api(user_id: int = Query(gt=0)):
    code = secrets.token_urlsafe(6)
    expires_at = int(time.time()) + 600

    create_link_code(code, user_id, expires_at)

    return {
        "code": code,
        "expires_in": 600
    }


@app.post("/link-vk", dependencies=[Depends(verify_api_key)])
def link_vk_api(data: VKLinkRequest):
    result = link_vk_account(
        data.code,
        data.vk_id,
        int(time.time())
    )

    if result == "invalid_or_expired":
        raise HTTPException(
            status_code=400,
            detail="Код недействителен или истёк"
        )

    if result == "already_linked":
        raise HTTPException(
            status_code=409,
            detail="Этот VK-аккаунт или аккаунт сайта уже привязан"
        )

    return {"message": "VK-аккаунт успешно привязан"}


@app.get("/users/by-vk/{vk_id}", dependencies=[Depends(verify_api_key)])
def get_user_by_vk_api(vk_id: int):
    user_id = get_user_id_by_vk(vk_id)

    if user_id is None:
        raise HTTPException(
            status_code=404,
            detail="VK-аккаунт не привязан"
        )

    return {"user_id": user_id}