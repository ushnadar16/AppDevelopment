"""FR-5.1 five-tier RBAC: HS256 JWTs and a data-driven policy matrix with tenant isolation."""
import base64
import hashlib
import hmac
import json
import os
import time

from .util import ApiError, salt

ROLES = ("super_admin", "league_organizer", "club_manager", "player", "viewer")

# Policy-as-data: action -> role -> scope rule. Missing role = denied.
POLICY = {
    "tenant.create":        {"super_admin": "any"},
    "league.fixtures.write": {"super_admin": "any", "league_organizer": "own_league"},
    "league.scoring.write": {"super_admin": "any", "league_organizer": "own_league"},
    "club.roster.write":    {"super_admin": "any", "club_manager": "own_club"},
    "club.products.write":  {"super_admin": "any", "club_manager": "own_club"},
    "player.update":        {"super_admin": "any", "club_manager": "own_club_player", "player": "self"},
    "club.read":            {r: ("any" if r == "super_admin" else "same_tenant") for r in ROLES},
    "platform.config.read": {"super_admin": "any"},
}


def _secret():
    explicit = os.environ.get("JWT_SECRET")
    if explicit:
        return explicit.encode()
    return hmac.new(salt().encode("utf-8") or b"dev", b"jwt-signing-key", hashlib.sha256).digest()


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def issue(user, ttl=12 * 3600):
    now = int(time.time())
    claims = {"sub": user["user_id"], "email": user["email"], "role": user["role"], "tenant_id": user["tenant_id"],
              "league_ids": user.get("league_ids", []), "club_id": user.get("club_id"),
              "player_id": user.get("player_id"), "iat": now, "exp": now + ttl}
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64(json.dumps(claims, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_secret(), f"{header}.{body}".encode(), hashlib.sha256).digest())
    return f"{header}.{body}.{sig}"


def unauthenticated(msg="Authentication required."):
    return ApiError(401, "UNAUTHENTICATED", msg, {})


def verify(auth_header):
    if not auth_header or not auth_header.startswith("Bearer "):
        raise unauthenticated()
    token = auth_header[7:].strip()
    parts = token.split(".")
    if len(parts) != 3:
        raise unauthenticated("Malformed token.")
    try:
        header = json.loads(_unb64(parts[0]))
        claims = json.loads(_unb64(parts[1]))
        sig = _unb64(parts[2])
    except Exception:
        raise unauthenticated("Malformed token.")
    if not isinstance(header, dict) or header.get("alg") != "HS256":
        raise unauthenticated("Unsupported token algorithm.")
    expected = hmac.new(_secret(), f"{parts[0]}.{parts[1]}".encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        raise unauthenticated("Invalid token signature.")
    if not isinstance(claims, dict) or not isinstance(claims.get("exp"), int) or claims["exp"] <= time.time():
        raise unauthenticated("Token expired.")
    if claims.get("role") not in ROLES:
        raise unauthenticated("Unknown role.")
    return claims


def forbidden():
    return ApiError(403, "FORBIDDEN", "You do not have permission to perform this action.", {})


def authorize(state, claims, action, resource=None):
    """resource: {"kind": "league"|"club"|"player", "id": ...} or None. Raises 403 on deny."""
    rule = POLICY.get(action, {}).get(claims["role"])
    if rule is None:
        raise forbidden()
    if rule == "any":
        return
    tenant = resource_tenant(state, resource)
    if tenant != claims.get("tenant_id"):
        raise forbidden()  # tenant isolation: cross-tenant is always 403
    rid = resource["id"] if resource else None
    if rule == "same_tenant":
        return
    if rule == "own_league" and rid in (claims.get("league_ids") or []):
        return
    if rule == "own_club" and rid == claims.get("club_id"):
        return
    if rule == "own_club_player" and state.players.get(rid, {}).get("club_id") == claims.get("club_id"):
        return
    if rule == "self" and rid == claims.get("player_id"):
        return
    raise forbidden()


def resource_tenant(state, resource):
    if resource is None:
        return None
    kind, rid = resource["kind"], resource["id"]
    table = {"league": state.rbac_leagues, "club": state.clubs, "player": state.players}[kind]
    item = table.get(rid)
    return item["tenant_id"] if item else None


def resource_exists(state, resource):
    kind, rid = resource["kind"], resource["id"]
    table = {"league": state.rbac_leagues, "club": state.clubs, "player": state.players}[kind]
    return rid in table


def hash_password(pw, salt_bytes=b"nascon-demo"):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt_bytes, 50_000).hex()
