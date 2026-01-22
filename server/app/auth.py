from datetime import datetime, timedelta, timezone
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError
import bcrypt

from .config import JWT_SECRET, JWT_ALG, ACCESS_TOKEN_MINUTES


def hash_password(p: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(p.encode("utf-8"), salt).decode("utf-8")


def verify_password(p: str, h: str) -> bool:
    return bcrypt.checkpw(p.encode("utf-8"), h.encode("utf-8"))


def create_access_token(payload: dict) -> str:
    # الأفضل exp يكون timezone-aware
    exp = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_MINUTES)
    to_encode = {**payload, "exp": exp}
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALG)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except ExpiredSignatureError:
        # خلّي deps.py يتعامل معها ويرجع 401 Token expired
        raise
    except JWTError:
        # أي JWT مشكلة ثانية: token invalid / signature wrong / malformed...
        raise
