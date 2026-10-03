"""Simple auth for hackathon demo.
Two roles: 'rm' and 'customer'.
In production replace with proper JWT + bcrypt.
"""
from __future__ import annotations
import hashlib, json, sqlite3
from contextlib import closing
from datetime import datetime, timezone
from . import config

DEMO_USERS = [
    {"id": "RM001", "email": "rm@finvision.demo", "password_hash": hashlib.sha256(b"RM@123").hexdigest(),
     "role": "rm", "name": "Priya Sharma", "customer_id": None},
    {"id": "RM002", "email": "rm2@finvision.demo", "password_hash": hashlib.sha256(b"RM@123").hexdigest(),
     "role": "rm", "name": "Arjun Mehta", "customer_id": None},
    {"id": "USR_C101", "email": "customer@finvision.demo", "password_hash": hashlib.sha256(b"Customer@123").hexdigest(),
     "role": "customer", "name": "Rahul Gupta", "customer_id": "C101"},
    {"id": "USR_C102", "email": "c102@finvision.demo", "password_hash": hashlib.sha256(b"Customer@123").hexdigest(),
     "role": "customer", "name": "Anita Singh", "customer_id": "C102"},
    {"id": "USR_C103", "email": "c103@finvision.demo", "password_hash": hashlib.sha256(b"Customer@123").hexdigest(),
     "role": "customer", "name": "Vikram Patel", "customer_id": "C103"},
]

# Simple in-memory session store (fine for hackathon)
_sessions: dict[str, dict] = {}


def login(email: str, password: str) -> dict | None:
    ph = hashlib.sha256(password.encode()).hexdigest()
    user = next((u for u in DEMO_USERS if u["email"] == email and u["password_hash"] == ph), None)
    if user is None:
        return None
    import secrets
    token = secrets.token_hex(32)
    _sessions[token] = {**user, "ts": datetime.now(timezone.utc).isoformat()}
    return {"token": token, "user": {k: user[k] for k in ("id", "email", "role", "name", "customer_id")}}


def get_user(token: str) -> dict | None:
    return _sessions.get(token)


def logout(token: str):
    _sessions.pop(token, None)


def list_demo_credentials() -> list[dict]:
    return [{"email": u["email"], "password": "RM@123" if u["role"] == "rm" else "Customer@123",
             "role": u["role"], "name": u["name"]} for u in DEMO_USERS]
