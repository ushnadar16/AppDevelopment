"""Shared helpers: error type, canonical JSON, HMAC signatures, validation."""
import hashlib
import hmac
import json
import os
import re
from datetime import date, datetime, timezone

ID_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,64}$")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ApiError(Exception):
    def __init__(self, status, code, message="", details=None, headers=None):
        super().__init__(message or code)
        self.status = status
        self.code = code
        self.message = message or code.replace("_", " ").capitalize()
        self.details = details if details is not None else {}
        self.headers = headers or {}

    def body(self):
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


def validation_error(fields, message="Request validation failed."):
    if isinstance(fields, str):
        fields = [fields]
    return ApiError(400, "VALIDATION_ERROR", message, {"fields": list(fields)})


def not_found(code, message, **details):
    return ApiError(404, code, message, details)


def conflict(code, message, **details):
    return ApiError(409, code, message, details)


def salt():
    return os.environ.get("DAY1_SALT", "")


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sign(id_, payload_obj, key=None):
    key = salt() if key is None else key
    msg = (id_ + "|" + canonical(payload_obj)).encode("utf-8")
    return hmac.new(key.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def lots_key(seed, league_id, team_id):
    return hashlib.sha256(f"{seed}|{league_id}|{team_id}".encode("utf-8")).hexdigest()


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today():
    return datetime.now(timezone.utc).date()


def is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def is_id(v):
    return isinstance(v, str) and bool(ID_RE.match(v))


def parse_date(v):
    if not isinstance(v, str) or not DATE_RE.match(v):
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        return None


def is_timestamp(v):
    if not isinstance(v, str) or not TS_RE.match(v):
        return False
    try:
        datetime.strptime(v, "%Y-%m-%dT%H:%M:%SZ")
        return True
    except ValueError:
        return False


def require_obj(v, field):
    if not isinstance(v, dict):
        raise validation_error(field)
    return v
