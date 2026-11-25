from __future__ import annotations
from contextlib import asynccontextmanager
import csv, io, hashlib, json, os, uuid, zipfile, secrets, time, logging
import urllib.error, urllib.parse, urllib.request
from datetime import date, datetime, timedelta, timezone
import jwt
from pathlib import Path
from math import isfinite
from fastapi import FastAPI, Depends, HTTPException, Query, Response, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi import UploadFile, File, Form
from sqlalchemy import select, func, update, text as sql_text
from sqlalchemy.orm import Session
from .config import settings
from .database import Base, get_engine, get_db, set_request_context, set_tenant_context
from .dependencies import get_current_user, require_roles
from .models import (Organization, User, RefreshToken, AuthActionToken, Supplier, PurchaseOrder, MaterialBatch,
    InventoryMovement, InventoryReconciliation, ProductionOrder, FinishedProductBatch, QualityInspection, Equipment, MaintenanceTask,
    TraceabilityEvent, Notification, AuditLog, Attachment, QualityTemplate, CorrectiveAction, FinishedProductSerial,
    EmailVerificationCode, OAuthLoginCode)
from .schemas import (LoginInput, OrganizationRegister, RefreshInput, LogoutInput, SupplierCreate, PurchaseOrderCreate,
    StatusUpdate, ReceiptCreate, InventoryAdjustment, ProductionCreate, ProductionProgress, InspectionCreate,
    EquipmentCreate, MaintenanceCreate, MaintenanceUpdate, LanguageUpdate, UserCreate, QualityRelease,
    EmailActionRequest, PasswordResetConfirm, InvitationCreate, InvitationAccept, QualityTemplateCreate,
    CorrectiveActionUpdate, SerialShipmentUpdate, InventoryReconciliationResolve,
    SupplierUpdate, PurchaseOrderUpdate, ProductionUpdate, EquipmentUpdate,
    MaintenanceDetailsUpdate, QualityTemplateUpdate, UserUpdate,
    EmailCodeRequest, EmailCodeVerify, GoogleExchangeInput, GoogleRegisterInput)
from .security import verify_password, create_access_token, create_refresh_token, hash_password
from .seed import seed
from .observability import configure_access_logger, RequestMetrics
from .object_storage import (
    StorageError, StorageObjectNotFound, delete_document, read_document,
    save_document, validate_storage_configuration,
)
from .malware_scanner import (
    MalwareDetected, MalwareScannerUnavailable, ping_malware_scanner,
    scan_document_bytes, validate_malware_scanner_configuration,
)
from .rate_limiting import enforce_api_rate_limit
from .nace_drex import triage_failed_inspection
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.environment.lower() == "production":
        if len(settings.jwt_secret_key.encode("utf-8")) < 32 or "local-development" in settings.jwt_secret_key or "replace-with" in settings.jwt_secret_key:
            raise RuntimeError("Production requires a strong unique JWT_SECRET_KEY (at least 32 bytes).")
        if settings.jwt_algorithm != "HS256":
            raise RuntimeError("Production requires JWT_ALGORITHM=HS256; asymmetric algorithms need a separately reviewed key-management design.")
        if "*" in settings.allowed_origins:
            raise RuntimeError("Wildcard CORS origins are not allowed in production.")
        from urllib.parse import urlsplit
        parsed_origins = [urlsplit(origin) for origin in settings.allowed_origins]
        if not parsed_origins or any(
            parsed.scheme != "https" or not parsed.netloc or parsed.path not in {"", "/"}
            or parsed.query or parsed.fragment or parsed.username or parsed.password
            for parsed in parsed_origins
        ):
            raise RuntimeError("Production requires exact HTTPS-only CORS_ORIGINS without paths, credentials, query strings or fragments.")
        from sqlalchemy.engine import make_url
        try:
            database_url = make_url(settings.database_url)
        except Exception as exc:
            raise RuntimeError("Production requires a valid PostgreSQL DATABASE_URL with TLS enabled.") from exc
        if database_url.drivername != "postgresql+psycopg" or database_url.query.get("sslmode") not in {"require", "verify-ca", "verify-full"}:
            raise RuntimeError("Production requires postgresql+psycopg DATABASE_URL with sslmode=require, verify-ca or verify-full.")
        if settings.allow_public_registration:
            raise RuntimeError("Production requires ALLOW_PUBLIC_REGISTRATION=false; use an approved onboarding process.")
        if settings.seed_demo_data:
            raise RuntimeError("Production requires SEED_DEMO_DATA=false; demo accounts must never be seeded in production.")
        if settings.expose_auth_action_links:
            raise RuntimeError("Production requires EXPOSE_AUTH_ACTION_LINKS=false.")
        if not settings.rate_limit_enabled or not settings.rate_limit_fail_closed:
            raise RuntimeError("Production requires enabled Redis API rate limiting with fail-closed behavior.")
        email_sender = settings.resend_from or settings.smtp_from
        if not (settings.smtp_host or settings.resend_api_key) or not email_sender or "factorylink.local" in email_sender.lower():
            raise RuntimeError("Production requires working email delivery (SMTP_HOST + SMTP_FROM, or RESEND_API_KEY + RESEND_FROM) with a non-local sender for verification codes, account recovery and invitations.")
        if settings.resend_api_key and settings.smtp_host and not settings.resend_from:
            raise RuntimeError("Production requires RESEND_FROM when RESEND_API_KEY is configured.")
        if bool(settings.google_client_id) != bool(settings.google_client_secret):
            raise RuntimeError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must either both be set or both be empty.")
        if settings.google_client_id and not settings.google_redirect_uri.startswith("https://"):
            raise RuntimeError("Production requires an HTTPS GOOGLE_REDIRECT_URI when Google sign-in is enabled.")
        if not settings.smtp_starttls:
            raise RuntimeError("Production requires SMTP_STARTTLS=true; plaintext SMTP is not permitted.")
        if bool(settings.smtp_username) != bool(settings.smtp_password):
            raise RuntimeError("Production SMTP_USERNAME and SMTP_PASSWORD must either both be set or both be empty.")
        if not settings.frontend_base_url.startswith("https://"):
            raise RuntimeError("Production requires HTTPS FRONTEND_BASE_URL for secure action links.")
        validate_storage_configuration(settings)
        validate_malware_scanner_configuration(settings)
    if settings.auto_create_schema:
        Base.metadata.create_all(bind=get_engine())
        if settings.seed_demo_data:
            seed()
    yield


def documentation_urls(environment: str) -> tuple[str | None, str | None, str | None]:
    if environment.lower() == "production":
        return None, None, None
    return "/docs", "/redoc", "/openapi.json"


docs_url, redoc_url, openapi_url = documentation_urls(settings.environment)
app = FastAPI(
    title="FactoryLink API",
    version="1.0.0",
    description="Manufacturing operations and supplier collaboration API",
    lifespan=lifespan,
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url,
)
access_logger = configure_access_logger(settings.log_level)
request_metrics = RequestMetrics()
app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"], allow_headers=["Authorization", "Content-Type", "Idempotency-Key"])

@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
    return response


@app.middleware("http")
async def request_observability(request: Request, call_next):
    """Attach a server-generated correlation id and emit a safe access record."""
    request_id = uuid.uuid4().hex
    started = time.perf_counter()
    try:
        if settings.rate_limit_enabled and request.url.path.startswith("/api/v1/"):
            try:
                retry_after = await enforce_api_rate_limit(request)
            except (RedisError, OSError, TimeoutError) as exc:
                access_logger.error("rate_limit_backend_unavailable", extra={"factorylink": {
                    "request_id": request_id,
                    "method": request.method,
                    "route": getattr(request.scope.get("route"), "path", "unmatched"),
                    "error_type": type(exc).__name__,
                }})
                if settings.rate_limit_fail_closed:
                    response = JSONResponse(
                        {"detail": "Request protection is temporarily unavailable; retry shortly."},
                        status_code=503,
                        headers={"Retry-After": "1"},
                    )
                else:
                    response = await call_next(request)
            else:
                if retry_after:
                    response = JSONResponse(
                        {"detail": "Too many requests; retry after the current rate-limit window."},
                        status_code=429,
                        headers={"Retry-After": str(retry_after)},
                    )
                else:
                    response = await call_next(request)
        else:
            response = await call_next(request)
    except Exception as exc:
        duration = time.perf_counter() - started
        route = getattr(request.scope.get("route"), "path", "unmatched")
        # Log the exception class only; never serialize request bodies, headers,
        # query strings, tokens, passwords or database connection details.
        access_logger.error("request_failed", extra={"factorylink": {
            "request_id": request_id,
            "method": request.method,
            "route": route,
            "status_code": 500,
            "duration_ms": round(duration * 1000, 3),
            "error_type": type(exc).__name__,
        }})
        request_metrics.observe(request.method, route, 500, duration)
        raise
    duration = time.perf_counter() - started
    route = getattr(request.scope.get("route"), "path", "unmatched")
    response.headers["X-Request-ID"] = request_id
    request_metrics.observe(request.method, route, response.status_code, duration)
    access_logger.info("request_completed", extra={"factorylink": {
        "request_id": request_id,
        "method": request.method,
        "route": route,
        "status_code": response.status_code,
        "duration_ms": round(duration * 1000, 3),
    }})
    return response


def check_readiness_dependencies() -> dict[str, str]:
    """Probe database and Redis without returning connection details to clients."""
    result: dict[str, str] = {}
    try:
        with get_engine().connect() as connection:
            connection.execute(sql_text("SELECT 1"))
        result["database"] = "ok"
    except Exception:
        result["database"] = "unavailable"
    client = None
    try:
        from redis import Redis
        client = Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        result["redis"] = "ok"
    except Exception:
        result["redis"] = "unavailable"
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
    result["malware_scanner"] = (
        "ok" if ping_malware_scanner(config=settings) else "unavailable"
    ) if settings.malware_scan_enabled else "not_required"
    return result

def audit(db: Session, user: User, action: str, entity_type: str, entity_id: str, payload: dict | None = None):
    db.add(AuditLog(organization_id=user.organization_id, user_id=user.id, action=action, entity_type=entity_type, entity_id=str(entity_id), payload=json.dumps(payload or {}, ensure_ascii=False)))


def notify(db: Session, org_id: int, title: str, body: str, level: str = "INFO"):
    db.add(Notification(organization_id=org_id, title=title, body=body, level=level))


def serialize(model):
    data = {c.name: getattr(model, c.name) for c in model.__table__.columns}
    return data


def parse_iso_date(value):
    return value.isoformat() if value else None


def evaluate_quality_criteria(criteria: list[dict], submitted: dict) -> tuple[dict, bool]:
    """Validate human-entered criterion results and derive non-conformance."""
    normalized: dict = {}
    failed = False
    for criterion in criteria:
        key = str(criterion.get("key", ""))
        kind = str(criterion.get("kind", "PASS_FAIL")).upper()
        required = bool(criterion.get("required", True))
        value = submitted.get(key)
        if value is None or value == "":
            if required:
                raise HTTPException(status_code=422, detail=f"Quality criterion '{criterion.get('label', key)}' is required")
            continue
        if kind == "PASS_FAIL":
            result = str(value).upper()
            if result not in {"PASS", "FAIL"}:
                raise HTTPException(status_code=422, detail=f"Quality criterion '{key}' must be PASS or FAIL")
            normalized[key] = result
            failed = failed or result == "FAIL"
        elif kind == "NUMERIC":
            try:
                number = float(value)
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail=f"Quality criterion '{key}' must be numeric")
            if not isfinite(number):
                raise HTTPException(status_code=422, detail=f"Quality criterion '{key}' must be finite")
            minimum, maximum = criterion.get("minimum"), criterion.get("maximum")
            normalized[key] = number
            if minimum is not None and number < float(minimum):
                failed = True
            if maximum is not None and number > float(maximum):
                failed = True
        elif kind == "TEXT":
            text_value = str(value).strip()
            if required and not text_value:
                raise HTTPException(status_code=422, detail=f"Quality criterion '{key}' cannot be empty")
            normalized[key] = text_value[:2000]
    unknown = set(submitted) - {str(item.get("key", "")) for item in criteria}
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown quality criterion keys: {', '.join(sorted(unknown))}")
    return normalized, failed


def is_supplier_account(user: User) -> bool:
    return user.role in {"SUPPLIER_USER", "SUPPLIER_ADMIN"}


def user_payload(db: Session, user: User):
    org = db.get(Organization, user.organization_id)
    return {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role, "language": user.language,
            "organization_id": user.organization_id, "organization_name": org.name if org else "", "timezone": org.timezone if org else "Asia/Tokyo", "currency": org.currency if org else "JPY"}


def add_refresh(db: Session, user: User):
    raw, digest, expires = create_refresh_token(user.id)
    record = RefreshToken(user_id=user.id, family_id=str(uuid.uuid4()), token_hash=digest, expires_at=expires)
    db.add(record)
    db.flush()
    return raw


def create_action_token(db: Session, user: User, purpose: str, expires_in: timedelta) -> tuple[str, AuthActionToken]:
    raw = secrets.token_urlsafe(40)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)
    # Invalidate previous outstanding actions of the same kind before issuing a new one.
    db.execute(
        update(AuthActionToken)
        .where(AuthActionToken.user_id == user.id, AuthActionToken.purpose == purpose, AuthActionToken.used_at.is_(None))
        .values(used_at=now)
    )
    row = AuthActionToken(
        organization_id=user.organization_id, user_id=user.id, purpose=purpose,
        token_hash=digest, expires_at=now + expires_in,
    )
    db.add(row)
    db.flush()
    return raw, row


def action_url(action: str, raw_token: str) -> str:
    from urllib.parse import urlencode
    return f"{settings.frontend_base_url.rstrip('/')}/?{urlencode({'action': action, 'token': raw_token})}"


def queue_action_email(to_email: str, subject: str, body: str) -> bool:
    """Deliver an email through the worker in production and directly elsewhere.

    A missing Celery broker or a delivery failure is logged and reported so a
    verification code is never silently dropped.
    """
    from .mailer import EmailDeliveryError, deliver_email, delivery_channel

    if not delivery_channel():
        logger.warning("Email delivery is not configured; '%s' was not sent to %s", subject, to_email)
        return False
    if settings.environment.lower() == "production":
        try:
            from .tasks import send_transactional_email
            send_transactional_email.delay(to_email, subject, body)
            return True
        except Exception:
            logger.exception("Email queue is unavailable; sending '%s' to %s directly", subject, to_email)
    try:
        deliver_email(to_email, subject, body)
        return True
    except EmailDeliveryError as exc:
        logger.error("Email delivery to %s failed: %s", to_email, exc)
    except Exception:
        logger.exception("Unexpected email delivery failure for %s", to_email)
    return False


def validate_action_token(db: Session, raw_token: str, purpose: str) -> tuple[AuthActionToken, User]:
    digest = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    set_request_context(db, "app.auth_action_token_hash", digest)
    row = db.scalar(
        select(AuthActionToken).where(
            AuthActionToken.token_hash == digest,
            AuthActionToken.purpose == purpose,
        ).with_for_update()
    )
    now = datetime.now(timezone.utc)
    if not row or row.used_at is not None or row.expires_at.replace(tzinfo=timezone.utc) <= now:
        raise HTTPException(status_code=400, detail="This link is invalid or has expired")
    set_request_context(db, "app.auth_user_id", str(row.user_id))
    user = db.get(User, row.user_id)
    if not user or user.organization_id != row.organization_id:
        raise HTTPException(status_code=400, detail="This link is invalid or has expired")
    set_tenant_context(db, user.organization_id)
    return row, user


EMAIL_CODE_TTL = timedelta(minutes=10)
EMAIL_CODE_TOKEN_TTL = timedelta(minutes=15)
EMAIL_CODE_MAX_ATTEMPTS = 5
EMAIL_CODE_RESEND_SECONDS = 60


def email_code_digest(email: str, purpose: str, code: str) -> str:
    return hashlib.sha256(f"{purpose}:{email}:{code}".encode("utf-8")).hexdigest()


def email_code_token_digest(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def issue_email_verification_code(db: Session, email: str, purpose: str) -> str:
    """Issue a six-digit code, replacing any outstanding code for this email."""
    now = datetime.now(timezone.utc)
    recent = db.scalar(select(EmailVerificationCode.id).where(
        EmailVerificationCode.email == email,
        EmailVerificationCode.purpose == purpose,
        EmailVerificationCode.created_at > now - timedelta(seconds=EMAIL_CODE_RESEND_SECONDS),
    ).limit(1))
    if recent:
        raise HTTPException(status_code=429, detail="A verification code was just sent. Wait a minute before requesting another.")
    db.execute(update(EmailVerificationCode).where(
        EmailVerificationCode.email == email,
        EmailVerificationCode.purpose == purpose,
        EmailVerificationCode.used_at.is_(None),
    ).values(used_at=now))
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(EmailVerificationCode(
        email=email, purpose=purpose, code_hash=email_code_digest(email, purpose, code),
        expires_at=now + EMAIL_CODE_TTL,
    ))
    db.flush()
    return code


def send_email_verification_code(email: str, purpose: str, code: str, full_name: str = "") -> bool:
    action = "create your FactoryLink workspace" if purpose == "REGISTRATION" else "reset your FactoryLink password"
    body = (
        f"Hello{(' ' + full_name) if full_name else ''},\n\n"
        f"Your verification code to {action} is:\n\n    {code}\n\n"
        "The code expires in 10 minutes and can be used once.\n\n"
        "If you did not request this, you can ignore this email.\n"
    )
    try:
        return queue_action_email(email, "FactoryLink verification code", body)
    except Exception:
        return False


def consume_email_verification(db: Session, email: str, purpose: str, raw_token: str) -> EmailVerificationCode:
    digest = email_code_token_digest(raw_token)
    row = db.scalar(select(EmailVerificationCode).where(
        EmailVerificationCode.email == email,
        EmailVerificationCode.purpose == purpose,
        EmailVerificationCode.verification_token_hash == digest,
    ).with_for_update())
    now = datetime.now(timezone.utc)
    if not row or row.used_at is not None or not row.token_expires_at or row.token_expires_at.replace(tzinfo=timezone.utc) <= now:
        raise HTTPException(status_code=400, detail="Email verification is invalid or has expired. Request a new code.")
    row.used_at = now
    return row


def consume_email_verification_by_token(db: Session, purpose: str, raw_token: str) -> EmailVerificationCode:
    digest = email_code_token_digest(raw_token)
    row = db.scalar(select(EmailVerificationCode).where(
        EmailVerificationCode.purpose == purpose,
        EmailVerificationCode.verification_token_hash == digest,
    ).with_for_update())
    now = datetime.now(timezone.utc)
    if not row or row.used_at is not None or not row.token_expires_at or row.token_expires_at.replace(tzinfo=timezone.utc) <= now:
        raise HTTPException(status_code=400, detail="Email verification is invalid or has expired. Request a new code.")
    row.used_at = now
    return row


GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_STATE_TTL = timedelta(minutes=10)
OAUTH_HANDOFF_TTL = timedelta(minutes=5)
GOOGLE_SIGNUP_TTL = timedelta(minutes=20)
_google_jwk_client = None


def google_sign_in_enabled() -> bool:
    return bool(settings.google_client_id and settings.google_client_secret)


def google_redirect_target(request: Request) -> str:
    """Configured callback URL; local development falls back to the API origin."""
    if settings.google_redirect_uri:
        return settings.google_redirect_uri
    return str(request.base_url).rstrip("/") + "/api/v1/auth/google/callback"


def frontend_redirect(**params: str) -> RedirectResponse:
    query = urllib.parse.urlencode({key: value for key, value in params.items() if value})
    return RedirectResponse(f"{settings.frontend_base_url.rstrip('/')}/?{query}", status_code=302)


def google_state_token() -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"type": "google_state", "nonce": secrets.token_urlsafe(16), "iat": now, "exp": now + GOOGLE_STATE_TTL},
        settings.jwt_secret_key, algorithm=settings.jwt_algorithm,
    )


def decode_google_state(state: str) -> None:
    try:
        claims = jwt.decode(state, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Google sign-in request is invalid or has expired") from exc
    if claims.get("type") != "google_state":
        raise HTTPException(status_code=400, detail="Google sign-in request is invalid or has expired")


def verify_google_id_token(raw_token: str) -> dict:
    """Validate Google's signature, issuer, audience and verified address."""
    global _google_jwk_client
    try:
        if _google_jwk_client is None:
            _google_jwk_client = jwt.PyJWKClient(GOOGLE_JWKS_URL, cache_keys=True)
        signing_key = _google_jwk_client.get_signing_key_from_jwt(raw_token).key
        claims = jwt.decode(
            raw_token, signing_key, algorithms=["RS256"], audience=settings.google_client_id,
            issuer=["https://accounts.google.com", "accounts.google.com"],
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Google identity could not be verified") from exc
    if not claims.get("sub") or not claims.get("email") or claims.get("email_verified") is not True:
        raise HTTPException(status_code=401, detail="Google did not confirm this email address")
    return claims


def exchange_google_code(code: str, redirect_uri: str) -> dict:
    payload = urllib.parse.urlencode({
        "code": code, "client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
        "redirect_uri": redirect_uri, "grant_type": "authorization_code",
    }).encode("utf-8")
    request = urllib.request.Request(
        GOOGLE_TOKEN_URL, data=payload, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            tokens = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Google rejected the sign-in attempt") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Google sign-in is temporarily unavailable") from exc
    id_token = tokens.get("id_token")
    if not id_token:
        raise HTTPException(status_code=502, detail="Google did not return an identity token")
    return verify_google_id_token(id_token)


def google_session_response(db: Session, user: User):
    set_tenant_context(db, user.organization_id)
    refresh = add_refresh(db, user)
    db.commit()
    return {"access_token": create_access_token(user.id, user.organization_id, user.role), "refresh_token": refresh,
        "token_type": "bearer", "user": user_payload(db, user)}


@app.get("/health")
@app.get("/health/live", include_in_schema=False)
def health():
    """Liveness probe: process is serving HTTP; no external dependencies."""
    return {"status": "ok", "service": "factorylink-api", "version": "1.0.0"}


@app.get("/health/ready", include_in_schema=False)
def readiness():
    """Readiness probe: database, Redis and enabled malware scanner must respond."""
    checks = check_readiness_dependencies()
    ready = all(value in {"ok", "not_required"} for value in checks.values()) and bool(checks)
    payload = {"status": "ready" if ready else "not_ready", "service": "factorylink-api", "checks": checks}
    return JSONResponse(payload, status_code=200 if ready else 503)


@app.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
def metrics():
    """Internal Prometheus text endpoint; keep API service on a private network."""
    return PlainTextResponse(request_metrics.render_prometheus(), media_type="text/plain; version=0.0.4; charset=utf-8")


@app.post("/api/v1/organizations/register", status_code=201)
def register_organization(payload: OrganizationRegister, db: Session = Depends(get_db)):
    """Create a new manufacturer or supplier tenant and its first administrator."""
    if not settings.allow_public_registration:
        raise HTTPException(status_code=403, detail="Public workspace registration is disabled; contact your administrator")
    set_request_context(db, "app.organization_provisioning", "on")
    if db.scalar(select(Organization).where(Organization.code == payload.organization_code)):
        raise HTTPException(status_code=409, detail="Organisation code is already registered")
    email = payload.email.strip().lower()
    set_request_context(db, "app.auth_email", email)
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status_code=409, detail="Email is already registered")
    # The address must have been confirmed with a code before the workspace and
    # its password are created; the ticket is single-use and expires quickly.
    consume_email_verification(db, email, "REGISTRATION", payload.email_verification_token)
    organization = Organization(
        name=payload.organization_name.strip(), code=payload.organization_code,
        org_type=payload.organization_type, postal_code=payload.postal_code,
        prefecture=payload.prefecture, timezone="Asia/Tokyo", currency="JPY",
    )
    db.add(organization); db.flush()
    # Registration is the one bootstrap path that has no access token yet.
    # Bind the newly-created tenant before inserting tenant-scoped audit data.
    set_tenant_context(db, organization.id)
    role = "ORG_ADMIN" if payload.organization_type == "MANUFACTURER" else "SUPPLIER_ADMIN"
    user = User(organization_id=organization.id, email=email, full_name=payload.owner_name.strip(),
        password_hash=hash_password(payload.password), role=role, language=payload.language)
    db.add(user); db.flush()
    audit(db, user, "REGISTER", "Organization", organization.id, {"organization_code": organization.code, "organization_type": organization.org_type})
    refresh = add_refresh(db, user)
    db.commit()
    return {"access_token": create_access_token(user.id, user.organization_id, user.role), "refresh_token": refresh,
        "token_type": "bearer", "user": user_payload(db, user)}


@app.post("/api/v1/auth/login")
def login(payload: LoginInput, db: Session = Depends(get_db)):
    set_request_context(db, "app.auth_email", payload.email.lower())
    user = db.scalar(select(User).where(func.lower(User.email) == payload.email.lower()))
    # Google-created accounts have no password until they set one by reset.
    if not user or not user.is_active or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    set_tenant_context(db, user.organization_id)
    refresh = add_refresh(db, user)
    db.commit()
    return {"access_token": create_access_token(user.id, user.organization_id, user.role), "refresh_token": refresh, "token_type": "bearer", "user": user_payload(db, user)}


@app.post("/api/v1/auth/refresh")
def refresh_session(payload: RefreshInput, db: Session = Depends(get_db)):
    digest = hashlib.sha256(payload.refresh_token.encode()).hexdigest()
    set_request_context(db, "app.auth_refresh_token_hash", digest)
    record = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == digest).with_for_update())
    now = datetime.now(timezone.utc)
    if not record:
        raise HTTPException(status_code=401, detail="Refresh token is invalid or expired")
    if record.revoked_at:
        # A rotated token being presented again is a replay signal. Revoke the
        # active descendants of this login, without disrupting other sessions.
        if record.replaced_by_id and record.family_id:
            set_request_context(db, "app.auth_user_id", str(record.user_id))
            replay_user = db.get(User, record.user_id)
            if replay_user:
                set_tenant_context(db, replay_user.organization_id)
            db.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == record.family_id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=now)
            )
            db.commit()
        raise HTTPException(status_code=401, detail="Refresh token reuse detected; sign in again")
    if record.expires_at.replace(tzinfo=timezone.utc) <= now:
        raise HTTPException(status_code=401, detail="Refresh token is invalid or expired")
    set_request_context(db, "app.auth_user_id", str(record.user_id))
    user = db.get(User, record.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User is inactive")
    set_tenant_context(db, user.organization_id)
    new_raw, new_hash, expires = create_refresh_token(user.id)
    replacement = RefreshToken(user_id=user.id, family_id=record.family_id, token_hash=new_hash, expires_at=expires)
    db.add(replacement); db.flush()
    record.revoked_at = now
    record.replaced_by_id = replacement.id
    db.commit()
    return {"access_token": create_access_token(user.id, user.organization_id, user.role), "refresh_token": new_raw, "token_type": "bearer", "user": user_payload(db, user)}


@app.post("/api/v1/auth/logout", status_code=204)
def logout(payload: LogoutInput, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    digest = hashlib.sha256(payload.refresh_token.encode()).hexdigest()
    record = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == digest, RefreshToken.user_id == user.id))
    if record and not record.revoked_at:
        record.revoked_at = datetime.now(timezone.utc)
        db.commit()
    return Response(status_code=204)


@app.post("/api/v1/auth/password-reset/request", status_code=202)
def request_password_reset(payload: EmailActionRequest, db: Session = Depends(get_db)):
    """Request a reset link without revealing whether the email exists."""
    set_request_context(db, "app.auth_email", payload.email.lower())
    user = db.scalar(select(User).where(func.lower(User.email) == payload.email.lower(), User.is_active.is_(True)))
    action_link = None
    if user:
        set_tenant_context(db, user.organization_id)
        raw, _ = create_action_token(db, user, "PASSWORD_RESET", timedelta(minutes=30))
        audit(db, user, "PASSWORD_RESET_REQUESTED", "User", user.id)
        db.commit()
        link = action_url("password-reset", raw)
        try:
            queued = queue_action_email(
                user.email,
                "FactoryLink password reset",
                f"Hello {user.full_name},\n\nUse this one-time link within 30 minutes to reset your FactoryLink password:\n{link}\n\nIf you did not request this, ignore this email.",
            )
        except Exception:
            # Keep response indistinguishable from an unknown account. The mail
            # worker logs delivery failures and retries independently.
            queued = False
        if not queued and settings.environment.lower() == "development" and settings.expose_auth_action_links:
            action_link = link
    response = {"message": "If an active account exists for that email, a reset link will be sent."}
    if action_link:
        response["development_action_link"] = action_link
    return response


@app.post("/api/v1/auth/password-reset/confirm")
def confirm_password_reset(payload: PasswordResetConfirm, db: Session = Depends(get_db)):
    """Complete a reset with either the emailed one-time link or a verified code."""
    if payload.verification_token:
        ticket = consume_email_verification_by_token(db, "PASSWORD_RESET", payload.verification_token)
        set_request_context(db, "app.auth_email", ticket.email)
        user = db.scalar(select(User).where(func.lower(User.email) == ticket.email, User.is_active.is_(True)))
        if not user:
            raise HTTPException(status_code=400, detail="Email verification is invalid or has expired. Request a new code.")
        set_tenant_context(db, user.organization_id)
        row = ticket
    else:
        row, user = validate_action_token(db, payload.token, "PASSWORD_RESET")
        if not user.is_active:
            raise HTTPException(status_code=400, detail="This link is invalid or has expired")
    now = datetime.now(timezone.utc)
    user.password_hash = hash_password(payload.password)
    row.used_at = now
    # A password reset invalidates every active refresh-token family for the user.
    db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=now))
    db.execute(
        update(AuthActionToken)
        .where(AuthActionToken.user_id == user.id, AuthActionToken.purpose == "PASSWORD_RESET", AuthActionToken.used_at.is_(None))
        .values(used_at=now)
    )
    db.execute(
        update(EmailVerificationCode)
        .where(EmailVerificationCode.email == user.email.lower(), EmailVerificationCode.purpose == "PASSWORD_RESET", EmailVerificationCode.used_at.is_(None))
        .values(used_at=now)
    )
    audit(db, user, "PASSWORD_RESET_COMPLETED", "User", user.id)
    db.commit()
    return {"message": "Password updated. Please sign in with your new password."}


@app.get("/api/v1/auth/me")
def me(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return user_payload(db, user)


@app.patch("/api/v1/auth/language")
def update_language(payload: LanguageUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    user.language = payload.language
    db.commit()
    return {"language": user.language}


@app.post("/api/v1/auth/email-verification/request", status_code=202)
def request_email_verification(payload: EmailCodeRequest, db: Session = Depends(get_db)):
    """Send a six-digit code for sign-up or password reset."""
    email = payload.email.strip().lower()
    set_request_context(db, "app.auth_email", email)
    user = None
    if payload.purpose == "REGISTRATION":
        if not settings.allow_public_registration:
            raise HTTPException(status_code=403, detail="Public workspace registration is disabled; contact your administrator")
        if db.scalar(select(User.id).where(func.lower(User.email) == email)):
            raise HTTPException(status_code=409, detail="Email is already registered")
    else:
        user = db.scalar(select(User).where(func.lower(User.email) == email, User.is_active.is_(True)))
        if user:
            set_tenant_context(db, user.organization_id)
            audit(db, user, "PASSWORD_RESET_CODE_REQUESTED", "User", user.id)
    code = None
    if payload.purpose == "REGISTRATION" or user:
        code = issue_email_verification_code(db, email, payload.purpose)
        db.commit()
        queued = send_email_verification_code(email, payload.purpose, code, user.full_name if user else "")
    else:
        # Unknown or inactive account: respond exactly like a known one so the
        # endpoint cannot be used to enumerate registered addresses.
        db.commit()
        queued = True
    response = {
        "message": "If the address can receive mail, a verification code has been sent.",
        "expires_in_seconds": int(EMAIL_CODE_TTL.total_seconds()),
    }
    if payload.purpose == "REGISTRATION":
        response["email_sent"] = bool(queued)
        if not queued:
            response["message"] = (
                "This server cannot send email yet, so the code was not delivered. "
                "Configure SMTP or Resend in the server environment."
            )
    # A password-reset response stays identical for unknown, inactive and
    # known addresses, so a delivery failure is never an existence oracle.
    if code and not queued and settings.environment.lower() == "development" and settings.expose_auth_action_links:
        response["development_code"] = code
    return response


@app.post("/api/v1/auth/email-verification/verify")
def verify_email_verification(payload: EmailCodeVerify, db: Session = Depends(get_db)):
    """Exchange a correct code for a short-lived verification ticket."""
    email = payload.email.strip().lower()
    set_request_context(db, "app.auth_email", email)
    now = datetime.now(timezone.utc)
    row = db.scalar(select(EmailVerificationCode).where(
        EmailVerificationCode.email == email,
        EmailVerificationCode.purpose == payload.purpose,
        EmailVerificationCode.verification_token_hash.is_(None),
        EmailVerificationCode.used_at.is_(None),
    ).order_by(EmailVerificationCode.created_at.desc()).with_for_update())
    if not row or row.expires_at.replace(tzinfo=timezone.utc) <= now:
        raise HTTPException(status_code=400, detail="Verification code is invalid or has expired. Request a new code.")
    if row.attempts >= EMAIL_CODE_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many incorrect attempts. Request a new code.")
    if not secrets.compare_digest(row.code_hash, email_code_digest(email, payload.purpose, payload.code)):
        row.attempts += 1
        db.commit()
        raise HTTPException(status_code=400, detail="Incorrect verification code")
    raw_token = secrets.token_urlsafe(32)
    row.verification_token_hash = email_code_token_digest(raw_token)
    row.token_expires_at = now + EMAIL_CODE_TOKEN_TTL
    db.commit()
    return {"verification_token": raw_token, "expires_in_seconds": int(EMAIL_CODE_TOKEN_TTL.total_seconds())}


@app.get("/api/v1/auth/providers")
def auth_providers():
    """Public sign-in capabilities so the UI never shows an unusable button."""
    return {"google": google_sign_in_enabled(), "password": True, "email_verification": True}


@app.get("/api/v1/auth/google/start", include_in_schema=False)
def google_start(request: Request):
    """Begin the Google OAuth authorization-code flow."""
    if not google_sign_in_enabled():
        raise HTTPException(status_code=503, detail="Google sign-in is not configured on this server")
    query = urllib.parse.urlencode({
        "client_id": settings.google_client_id,
        "redirect_uri": google_redirect_target(request),
        "response_type": "code",
        "scope": "openid email profile",
        "state": google_state_token(),
        "prompt": "select_account",
    })
    return RedirectResponse(f"{GOOGLE_AUTHORIZE_URL}?{query}", status_code=302)


@app.get("/api/v1/auth/google/callback", include_in_schema=False)
def google_callback(request: Request, code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db)):
    """Exchange Google's code on the server, then hand the browser a one-time code."""
    if error:
        return frontend_redirect(google_error="access_denied")
    if not google_sign_in_enabled():
        return frontend_redirect(google_error="not_configured")
    if not code:
        return frontend_redirect(google_error="google_failed")
    try:
        decode_google_state(state)
        claims = exchange_google_code(code, google_redirect_target(request))
    except HTTPException:
        return frontend_redirect(google_error="google_failed")
    email = str(claims["email"]).strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user and not user.is_active:
        return frontend_redirect(google_error="account_inactive")
    raw = secrets.token_urlsafe(32)
    db.add(OAuthLoginCode(
        code_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        purpose="SIGNIN" if user else "SIGNUP",
        user_id=user.id if user else None,
        email=email,
        full_name=str(claims.get("name") or "")[:140],
        google_sub=str(claims["sub"])[:64],
        expires_at=datetime.now(timezone.utc) + OAUTH_HANDOFF_TTL,
    ))
    db.commit()
    return frontend_redirect(google_code=raw)


@app.post("/api/v1/auth/google/exchange")
def google_exchange(payload: GoogleExchangeInput, db: Session = Depends(get_db)):
    """Trade the one-time hand-off code for a session or a sign-up token."""
    digest = hashlib.sha256(payload.code.encode("utf-8")).hexdigest()
    row = db.scalar(select(OAuthLoginCode).where(OAuthLoginCode.code_hash == digest).with_for_update())
    now = datetime.now(timezone.utc)
    if not row or row.used_at is not None or row.expires_at.replace(tzinfo=timezone.utc) <= now:
        raise HTTPException(status_code=400, detail="Google sign-in has expired. Please try again.")
    row.used_at = now
    if row.purpose == "SIGNIN":
        user = db.get(User, row.user_id) if row.user_id else None
        if not user or not user.is_active:
            db.commit()
            raise HTTPException(status_code=401, detail="This account is not active")
        if not user.google_sub:
            user.google_sub = row.google_sub
            audit(db, user, "GOOGLE_LINKED", "User", user.id)
        return google_session_response(db, user)
    signup_token = jwt.encode(
        {"type": "google_signup", "email": row.email, "full_name": row.full_name, "sub": row.google_sub,
         "iat": now, "exp": now + GOOGLE_SIGNUP_TTL},
        settings.jwt_secret_key, algorithm=settings.jwt_algorithm,
    )
    db.commit()
    return {"needs_registration": True, "signup_token": signup_token, "email": row.email, "full_name": row.full_name}


@app.post("/api/v1/auth/google/register", status_code=201)
def google_register(payload: GoogleRegisterInput, db: Session = Depends(get_db)):
    """Finish a Google sign-up by creating the workspace without a password."""
    if not settings.allow_public_registration:
        raise HTTPException(status_code=403, detail="Public workspace registration is disabled; contact your administrator")
    try:
        claims = jwt.decode(payload.signup_token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Google sign-up has expired. Please start again.") from exc
    if claims.get("type") != "google_signup" or not claims.get("email") or not claims.get("sub"):
        raise HTTPException(status_code=400, detail="Google sign-up has expired. Please start again.")
    email = str(claims["email"]).strip().lower()
    set_request_context(db, "app.organization_provisioning", "on")
    set_request_context(db, "app.auth_email", email)
    if db.scalar(select(Organization).where(Organization.code == payload.organization_code)):
        raise HTTPException(status_code=409, detail="Organisation code is already registered")
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status_code=409, detail="Email is already registered")
    organization = Organization(
        name=payload.organization_name.strip(), code=payload.organization_code,
        org_type=payload.organization_type, postal_code=payload.postal_code,
        prefecture=payload.prefecture, timezone="Asia/Tokyo", currency="JPY",
    )
    db.add(organization); db.flush()
    set_tenant_context(db, organization.id)
    role = "ORG_ADMIN" if payload.organization_type == "MANUFACTURER" else "SUPPLIER_ADMIN"
    user = User(
        organization_id=organization.id, email=email, full_name=payload.owner_name.strip(),
        password_hash=None, google_sub=str(claims["sub"])[:64], role=role, language=payload.language,
    )
    db.add(user); db.flush()
    audit(db, user, "REGISTER", "Organization", organization.id,
          {"organization_code": organization.code, "organization_type": organization.org_type, "method": "GOOGLE"})
    refresh = add_refresh(db, user)
    db.commit()
    return {"access_token": create_access_token(user.id, user.organization_id, user.role), "refresh_token": refresh,
        "token_type": "bearer", "user": user_payload(db, user)}


@app.get("/api/v1/users")
def list_users(db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "SUPPLIER_ADMIN"))):
    rows = db.scalars(select(User).where(User.organization_id == user.organization_id, User.is_active.is_(True)).order_by(User.full_name)).all()
    return [{"id": x.id, "email": x.email, "full_name": x.full_name, "role": x.role, "language": x.language, "is_active": x.is_active, "created_at": x.created_at.isoformat()} for x in rows]


@app.post("/api/v1/users/invitations", status_code=202)
def invite_user(payload: InvitationCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "SUPPLIER_ADMIN"))):
    organization = db.get(Organization, user.organization_id)
    if not organization:
        raise HTTPException(status_code=404, detail="Organisation not found")
    factory_roles = {"ORG_ADMIN", "PRODUCTION_MANAGER", "WAREHOUSE_MANAGER", "QUALITY_INSPECTOR", "MAINTENANCE_MANAGER", "OPERATOR"}
    allowed_roles = factory_roles if organization.org_type == "MANUFACTURER" else {"SUPPLIER_USER"}
    if payload.role not in allowed_roles:
        raise HTTPException(status_code=422, detail="Role is not valid for this organisation type")
    email = payload.email.lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(status_code=409, detail="Email is already registered")
    # Inactive account cannot authenticate until the one-time invitation is accepted.
    row = User(
        organization_id=user.organization_id, email=email, full_name=payload.full_name.strip(),
        password_hash=hash_password(secrets.token_urlsafe(48)), role=payload.role,
        language=payload.language, is_active=False,
    )
    db.add(row); db.flush()
    raw, _ = create_action_token(db, row, "INVITATION", timedelta(days=7))
    audit(db, user, "INVITE", "User", row.id, {"email": row.email, "role": row.role})
    db.commit()
    link = action_url("accept-invitation", raw)
    try:
        queued = queue_action_email(
            row.email,
            "You are invited to FactoryLink",
            f"Hello {row.full_name},\n\n{user.full_name} invited you to join {organization.name} on FactoryLink. Accept this one-time invitation within 7 days:\n{link}",
        )
    except Exception:
        queued = False
    response = {"id": row.id, "email": row.email, "full_name": row.full_name, "role": row.role, "status": "INVITED"}
    if not queued and settings.environment.lower() == "development" and settings.expose_auth_action_links:
        response["development_action_link"] = link
    return response


@app.post("/api/v1/users/invitations/accept")
def accept_invitation(payload: InvitationAccept, db: Session = Depends(get_db)):
    row, invited_user = validate_action_token(db, payload.token, "INVITATION")
    if invited_user.is_active:
        raise HTTPException(status_code=409, detail="This account is already active")
    now = datetime.now(timezone.utc)
    invited_user.password_hash = hash_password(payload.password)
    invited_user.is_active = True
    row.used_at = now
    db.execute(
        update(AuthActionToken)
        .where(AuthActionToken.user_id == invited_user.id, AuthActionToken.purpose == "INVITATION", AuthActionToken.used_at.is_(None))
        .values(used_at=now)
    )
    set_tenant_context(db, invited_user.organization_id)
    audit(db, invited_user, "INVITATION_ACCEPTED", "User", invited_user.id)
    refresh = add_refresh(db, invited_user)
    db.commit()
    return {
        "access_token": create_access_token(invited_user.id, invited_user.organization_id, invited_user.role),
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": user_payload(db, invited_user),
    }


@app.post("/api/v1/users", status_code=410, deprecated=True)
def create_user_legacy():
    raise HTTPException(status_code=410, detail="Direct password assignment is disabled. Use POST /api/v1/users/invitations.")


@app.get("/api/v1/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    oid = user.organization_id
    if is_supplier_account(user):
        raise HTTPException(status_code=403, detail="Supplier accounts use the supplier dashboard")
    orders = db.scalars(select(ProductionOrder).where(ProductionOrder.organization_id == oid)).all()
    batches = db.scalars(select(MaterialBatch).where(MaterialBatch.organization_id == oid)).all()
    inspections = db.scalars(select(QualityInspection).where(QualityInspection.organization_id == oid)).all()
    equipment = db.scalars(select(Equipment).where(Equipment.organization_id == oid)).all()
    purchase_orders = db.scalars(select(PurchaseOrder).where(PurchaseOrder.organization_id == oid)).all()
    today = date.today()
    total_orders = len(orders)
    completed = sum(1 for x in orders if x.status == "COMPLETED")
    delayed = sum(1 for x in orders if x.due_date and x.due_date < today and x.status not in ("COMPLETED", "CANCELLED"))
    total_qty = sum(x.quantity for x in orders)
    completed_qty = sum(x.completed_quantity for x in orders)
    total_defects = sum(x.defect_count for x in inspections)
    inspected_units = sum(x.sample_size for x in inspections)
    inventory_value = sum(max(0, b.quantity_on_hand) * b.unit_cost for b in batches)
    low_stock = [serialize(b) for b in batches if b.quantity_on_hand - b.quantity_reserved < max(1, b.quantity_on_hand * .15)]
    due_maintenance = [serialize(t) for t in db.scalars(select(MaintenanceTask).where(MaintenanceTask.organization_id == oid, MaintenanceTask.status.in_(["OVERDUE", "SCHEDULED"]))).all() if not t.due_date or t.due_date <= today + timedelta(days=7)]
    recent = db.scalars(select(AuditLog).where(AuditLog.organization_id == oid).order_by(AuditLog.created_at.desc()).limit(8)).all()
    return {
        "kpis": {"production_orders": total_orders, "completed_orders": completed, "delayed_orders": delayed,
                 "production_progress": round((completed_qty / total_qty * 100) if total_qty else 0, 1),
                 "defect_rate": round((total_defects / max(1, inspected_units)) * 100, 2), "inventory_value": round(inventory_value, 2),
                 "low_stock_count": len(low_stock), "open_purchase_orders": sum(1 for p in purchase_orders if p.status not in ("DELIVERED", "CANCELLED")),
                 "equipment_count": len(equipment), "equipment_due": sum(1 for e in equipment if e.status == "MAINTENANCE_DUE")},
        "production_status": [{"status": s, "count": sum(1 for o in orders if o.status == s)} for s in ["PLANNED", "READY", "IN_PROGRESS", "PAUSED", "COMPLETED", "CANCELLED"]],
        "production_orders": [serialize(x) for x in orders[:6]], "low_stock": low_stock[:6], "maintenance_due": due_maintenance[:6],
        "recent_activity": [{"action": x.action, "entity_type": x.entity_type, "entity_id": x.entity_id, "created_at": x.created_at.isoformat()} for x in recent]
    }


@app.get("/api/v1/suppliers")
def list_suppliers(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if is_supplier_account(user):
        raise HTTPException(status_code=403, detail="Supplier users cannot browse the supplier directory")
    rows = db.scalars(select(Supplier).where(Supplier.organization_id == user.organization_id).order_by(Supplier.name)).all()
    return [serialize(x) for x in rows]


@app.post("/api/v1/suppliers", status_code=201)
def create_supplier(payload: SupplierCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "PRODUCTION_MANAGER"))):
    existing = db.scalar(select(Supplier).where(Supplier.organization_id == user.organization_id, Supplier.code == payload.code))
    if existing:
        raise HTTPException(status_code=409, detail="Supplier code already exists")
    data = payload.model_dump(exclude={"supplier_organization_code"})
    partner_code = payload.supplier_organization_code.strip().upper()
    if partner_code:
        set_request_context(db, "app.supplier_organization_code", partner_code)
        partner = db.scalar(select(Organization).where(Organization.code == partner_code, Organization.org_type == "SUPPLIER"))
        if not partner:
            raise HTTPException(status_code=404, detail="Supplier organisation code was not found")
        data["supplier_organization_id"] = partner.id
    row = Supplier(organization_id=user.organization_id, **data)
    db.add(row); db.flush(); audit(db, user, "CREATE", "Supplier", row.id, {"code": row.code, "linked_supplier_organization_id": row.supplier_organization_id}); db.commit()
    return serialize(row)


@app.get("/api/v1/purchase-orders")
def list_purchase_orders(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if is_supplier_account(user):
        supplier_ids = select(Supplier.id).where(Supplier.supplier_organization_id == user.organization_id)
        rows = db.scalars(select(PurchaseOrder).where(PurchaseOrder.supplier_id.in_(supplier_ids)).order_by(PurchaseOrder.created_at.desc())).all()
    else:
        rows = db.scalars(select(PurchaseOrder).where(PurchaseOrder.organization_id == user.organization_id).order_by(PurchaseOrder.created_at.desc())).all()
    return [{**serialize(row), "received_quantity": float(row.received_quantity or 0.0),
             "remaining_quantity": max(0.0, row.quantity - float(row.received_quantity or 0.0))} for row in rows]


@app.post("/api/v1/purchase-orders", status_code=201)
def create_purchase_order(payload: PurchaseOrderCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "PRODUCTION_MANAGER"))):
    supplier = db.scalar(select(Supplier).where(Supplier.id == payload.supplier_id, Supplier.organization_id == user.organization_id, Supplier.status == "ACTIVE"))
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    if db.scalar(select(PurchaseOrder).where(PurchaseOrder.organization_id == user.organization_id, PurchaseOrder.po_number == payload.po_number)):
        raise HTTPException(status_code=409, detail="Purchase order number already exists")
    row = PurchaseOrder(organization_id=user.organization_id, **payload.model_dump())
    db.add(row); db.flush(); audit(db, user, "CREATE", "PurchaseOrder", row.id, {"po_number": row.po_number})
    if supplier.supplier_organization_id:
        notify(db, supplier.supplier_organization_id, "New purchase order", f"{row.po_number} has been shared with your organisation.")
    db.commit(); return serialize(row)


@app.patch("/api/v1/purchase-orders/{po_id}/status")
def update_purchase_order(po_id: int, payload: StatusUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.get(PurchaseOrder, po_id)
    if not row:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    if is_supplier_account(user):
        supplier = db.scalar(select(Supplier).where(Supplier.id == row.supplier_id, Supplier.supplier_organization_id == user.organization_id))
        # Suppliers confirm and dispatch. Actual received/delivered quantities are recorded by the factory.
        allowed = {"SUBMITTED": {"CONFIRMED"}, "CONFIRMED": {"IN_TRANSIT"}, "PARTIALLY_DELIVERED": {"IN_TRANSIT"}}
        if not supplier or payload.status not in allowed.get(row.status, set()):
            raise HTTPException(status_code=403, detail="Supplier cannot make this purchase-order transition")
    else:
        if row.organization_id != user.organization_id or user.role not in {"ORG_ADMIN", "PRODUCTION_MANAGER", "WAREHOUSE_MANAGER"}:
            raise HTTPException(status_code=403, detail="Not permitted")
        allowed = {"DRAFT": {"SUBMITTED", "CANCELLED"}, "SUBMITTED": {"CONFIRMED", "CANCELLED"}, "CONFIRMED": {"CANCELLED"}, "IN_TRANSIT": {"CANCELLED"}, "PARTIALLY_DELIVERED": {"CANCELLED"}}
        if payload.status not in allowed.get(row.status, set()):
            raise HTTPException(status_code=409, detail=f"Invalid transition: {row.status} → {payload.status}")
    row.status = payload.status
    if payload.note:
        row.supplier_note = payload.note[:2000]
    audit(db, user, "STATUS_CHANGE", "PurchaseOrder", row.id, {"status": row.status})
    notify(db, row.organization_id, "Purchase order updated", f"{row.po_number} status changed to {row.status}.", "INFO")
    db.commit(); return serialize(row)


@app.get("/api/v1/inventory/batches")
def list_batches(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if is_supplier_account(user):
        raise HTTPException(status_code=403, detail="Not permitted")
    rows = db.scalars(select(MaterialBatch).where(MaterialBatch.organization_id == user.organization_id).order_by(MaterialBatch.received_at.desc())).all()
    return [serialize(x) for x in rows]


@app.post("/api/v1/inventory/receipts", status_code=201)
def receive_material(payload: ReceiptCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "WAREHOUSE_MANAGER"))):
    lot_number = payload.lot_number.strip()
    material_name = payload.material_name.strip()
    unit = payload.unit.strip()
    existing = db.scalar(select(MaterialBatch).where(MaterialBatch.organization_id == user.organization_id, MaterialBatch.lot_number == lot_number))
    if existing:
        raise HTTPException(status_code=409, detail="Lot number already exists; duplicate receipt prevented")
    # A material uses one canonical unit in an organisation; otherwise FIFO reservations
    # could accidentally combine kilograms and pieces as though they were interchangeable.
    mismatched_unit = db.scalar(select(MaterialBatch.id).where(
        MaterialBatch.organization_id == user.organization_id,
        func.lower(MaterialBatch.material_name) == material_name.lower(),
        MaterialBatch.unit != unit,
    ).limit(1))
    if mismatched_unit:
        raise HTTPException(status_code=409, detail="This material already uses a different unit of measure in the organisation")

    purchase_order = None
    supplier_id = payload.supplier_id
    if payload.purchase_order_id:
        purchase_order = db.scalar(select(PurchaseOrder).where(
            PurchaseOrder.id == payload.purchase_order_id,
            PurchaseOrder.organization_id == user.organization_id,
        ).with_for_update())
        if not purchase_order:
            raise HTTPException(status_code=404, detail="Purchase order not found")
        if purchase_order.status != "IN_TRANSIT":
            raise HTTPException(status_code=409, detail="Supplier must dispatch the purchase order before the factory can record a receipt")
        if supplier_id and supplier_id != purchase_order.supplier_id:
            raise HTTPException(status_code=422, detail="Supplier does not match the purchase order")
        if material_name.casefold() != purchase_order.item_name.strip().casefold():
            raise HTTPException(status_code=422, detail="Material name must match the purchase-order item")
        if unit.casefold() != purchase_order.unit.strip().casefold():
            raise HTTPException(status_code=422, detail="Unit of measure must match the purchase order")
        supplier_id = purchase_order.supplier_id
        # The locked PO row is the canonical cumulative receipt counter. This
        # keeps supplier-visible receipt progress independent of factory ledger
        # access and serializes concurrent partial receipts on PostgreSQL.
        received_before = float(purchase_order.received_quantity or 0.0)
        if received_before + payload.quantity > purchase_order.quantity + 1e-9:
            remaining = max(0.0, purchase_order.quantity - received_before)
            raise HTTPException(status_code=409, detail=f"Receipt exceeds remaining purchase-order quantity ({remaining:g} {purchase_order.unit})")
    elif supplier_id and not db.scalar(select(Supplier).where(Supplier.id == supplier_id, Supplier.organization_id == user.organization_id)):
        raise HTTPException(status_code=404, detail="Supplier not found")

    batch = MaterialBatch(organization_id=user.organization_id, supplier_id=supplier_id,
        purchase_order_id=purchase_order.id if purchase_order else None, material_name=material_name,
        lot_number=lot_number, quantity_on_hand=payload.quantity, unit=unit,
        unit_cost=payload.unit_cost, status="AVAILABLE")
    db.add(batch); db.flush()
    movement = InventoryMovement(organization_id=user.organization_id, batch_id=batch.id, movement_type="RECEIPT", quantity=payload.quantity, reference=payload.reference, note="Goods receipt", created_by=user.id)
    db.add(movement)
    db.add(TraceabilityEvent(organization_id=user.organization_id, lot_number=batch.lot_number, event_type="GOODS_RECEIVED", reference=payload.reference,
        details=f"Received {payload.quantity:g} {unit} of {material_name}" + (f" against {purchase_order.po_number}" if purchase_order else "")))
    audit(db, user, "RECEIPT", "MaterialBatch", batch.id, {"lot_number": batch.lot_number, "quantity": payload.quantity, "purchase_order_id": purchase_order.id if purchase_order else None})
    notify(db, user.organization_id, "Inventory received", f"{material_name} · {lot_number} received.", "SUCCESS")
    if purchase_order:
        received_after = received_before + payload.quantity
        purchase_order.received_quantity = received_after
        purchase_order.status = "DELIVERED" if received_after + 1e-9 >= purchase_order.quantity else "PARTIALLY_DELIVERED"
        audit(db, user, "GOODS_RECEIPT", "PurchaseOrder", purchase_order.id,
              {"po_number": purchase_order.po_number, "received_quantity": payload.quantity, "cumulative_received": received_after, "status": purchase_order.status})
        supplier = db.get(Supplier, purchase_order.supplier_id)
        if supplier and supplier.supplier_organization_id:
            notify(db, supplier.supplier_organization_id, "Goods receipt recorded", f"{purchase_order.po_number}: {payload.quantity:g} {purchase_order.unit} received by the factory.", "SUCCESS")
    db.commit(); return serialize(batch)


@app.post("/api/v1/inventory/adjustments", status_code=201)
def adjust_inventory(payload: InventoryAdjustment, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "WAREHOUSE_MANAGER"))):
    batch = db.scalar(select(MaterialBatch).where(
        MaterialBatch.id == payload.batch_id,
        MaterialBatch.organization_id == user.organization_id,
    ).with_for_update())
    if not batch:
        raise HTTPException(status_code=404, detail="Material batch not found")
    new_quantity = batch.quantity_on_hand + payload.quantity_delta
    if new_quantity < batch.quantity_reserved:
        raise HTTPException(status_code=409, detail="Adjustment would reduce stock below the quantity reserved for production")
    if new_quantity < 0:
        raise HTTPException(status_code=409, detail="Adjustment would create negative stock")
    batch.quantity_on_hand = new_quantity
    movement_type = "ADJUSTMENT_IN" if payload.quantity_delta > 0 else "ADJUSTMENT_OUT"
    db.add(InventoryMovement(
        organization_id=user.organization_id, batch_id=batch.id, movement_type=movement_type,
        quantity=payload.quantity_delta, reference=payload.reference, note=payload.reason,
        created_by=user.id,
    ))
    db.add(TraceabilityEvent(
        organization_id=user.organization_id, lot_number=batch.lot_number,
        event_type="INVENTORY_ADJUSTMENT", reference=payload.reference,
        details=f"{payload.quantity_delta:+g} {batch.unit}: {payload.reason}",
    ))
    audit(db, user, "INVENTORY_ADJUSTMENT", "MaterialBatch", batch.id, {
        "quantity_delta": payload.quantity_delta, "reference": payload.reference, "reason": payload.reason,
    })
    notify(db, user.organization_id, "Inventory adjusted", f"{batch.lot_number}: {payload.quantity_delta:+g} {batch.unit}.", "WARNING")
    db.commit()
    return serialize(batch)


def inventory_ledger_quantity(db: Session, batch_id: int) -> float:
    return float(db.scalar(
        select(func.coalesce(func.sum(InventoryMovement.quantity), 0.0))
        .where(InventoryMovement.batch_id == batch_id)
    ) or 0.0)


@app.get("/api/v1/inventory/reconciliations")
def list_inventory_reconciliations(
    status_filter: str | None = Query(default=None, alias="status", pattern="^(OPEN|RESOLVED)$"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ORG_ADMIN", "WAREHOUSE_MANAGER")),
):
    query = select(InventoryReconciliation).where(
        InventoryReconciliation.organization_id == user.organization_id,
    )
    if status_filter:
        query = query.where(InventoryReconciliation.status == status_filter)
    rows = db.scalars(query.order_by(InventoryReconciliation.detected_at.desc()).limit(500)).all()
    return [serialize(row) for row in rows]


@app.post("/api/v1/inventory/reconciliations", status_code=201)
def detect_inventory_reconciliation(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ORG_ADMIN", "WAREHOUSE_MANAGER")),
):
    batches = db.scalars(
        select(MaterialBatch)
        .where(MaterialBatch.organization_id == user.organization_id)
        .order_by(MaterialBatch.id)
        .with_for_update()
    ).all()
    discrepancies: list[InventoryReconciliation] = []
    checked_at = datetime.now(timezone.utc)
    for batch in batches:
        ledger_quantity = inventory_ledger_quantity(db, batch.id)
        if abs(float(batch.quantity_on_hand) - ledger_quantity) <= 1e-9:
            continue
        row = db.scalar(
            select(InventoryReconciliation)
            .where(
                InventoryReconciliation.organization_id == user.organization_id,
                InventoryReconciliation.batch_id == batch.id,
                InventoryReconciliation.status == "OPEN",
            )
            .with_for_update()
        )
        if row is None:
            row = InventoryReconciliation(
                organization_id=user.organization_id,
                batch_id=batch.id,
                observed_quantity=batch.quantity_on_hand,
                ledger_quantity=ledger_quantity,
                variance=float(batch.quantity_on_hand) - ledger_quantity,
                status="OPEN",
                detected_by=user.id,
                detected_at=checked_at,
            )
            db.add(row)
        else:
            row.observed_quantity = batch.quantity_on_hand
            row.ledger_quantity = ledger_quantity
            row.variance = float(batch.quantity_on_hand) - ledger_quantity
            row.detected_by = user.id
            row.detected_at = checked_at
        discrepancies.append(row)
    db.flush()
    response = {
        "batches_checked": len(batches),
        "discrepancies": [serialize(row) for row in discrepancies],
    }
    audit(db, user, "INVENTORY_RECONCILIATION_SCAN", "Inventory", "all", {
        "batches_checked": len(batches),
        "discrepancies_found": len(discrepancies),
    })
    db.commit()
    return response


@app.post("/api/v1/inventory/reconciliations/{reconciliation_id}/resolve")
def resolve_inventory_reconciliation(
    reconciliation_id: int,
    payload: InventoryReconciliationResolve,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ORG_ADMIN", "WAREHOUSE_MANAGER")),
):
    reconciliation = db.scalar(
        select(InventoryReconciliation)
        .where(
            InventoryReconciliation.id == reconciliation_id,
            InventoryReconciliation.organization_id == user.organization_id,
        )
    )
    if not reconciliation:
        raise HTTPException(status_code=404, detail="Inventory reconciliation not found")
    batch = db.scalar(
        select(MaterialBatch)
        .where(
            MaterialBatch.id == reconciliation.batch_id,
            MaterialBatch.organization_id == user.organization_id,
        )
        .with_for_update()
    )
    if not batch:
        raise HTTPException(status_code=409, detail="Reconciliation batch is no longer available")
    # Scans lock the batch before its open reconciliation row. Keep the same
    # order here so a concurrent scan and correction cannot deadlock.
    reconciliation = db.scalar(
        select(InventoryReconciliation)
        .where(
            InventoryReconciliation.id == reconciliation_id,
            InventoryReconciliation.organization_id == user.organization_id,
            InventoryReconciliation.batch_id == batch.id,
        )
        .with_for_update()
    )
    if not reconciliation:
        raise HTTPException(status_code=404, detail="Inventory reconciliation not found")
    if reconciliation.status != "OPEN":
        raise HTTPException(status_code=409, detail="Inventory reconciliation is already resolved")
    ledger_quantity = inventory_ledger_quantity(db, batch.id)
    if abs(float(batch.quantity_on_hand) - ledger_quantity) <= 1e-9:
        raise HTTPException(status_code=409, detail="The discrepancy changed; run reconciliation again before correcting it")
    if payload.counted_quantity < float(batch.quantity_reserved):
        raise HTTPException(status_code=409, detail="Counted quantity cannot be below stock reserved for production")

    previous_quantity = float(batch.quantity_on_hand)
    adjustment_quantity = payload.counted_quantity - ledger_quantity
    batch.quantity_on_hand = payload.counted_quantity
    movement = None
    if abs(adjustment_quantity) > 1e-9:
        movement = InventoryMovement(
            organization_id=user.organization_id,
            batch_id=batch.id,
            movement_type="ADJUSTMENT_IN" if adjustment_quantity > 0 else "ADJUSTMENT_OUT",
            quantity=adjustment_quantity,
            reference=payload.reference,
            note=f"Inventory reconciliation {reconciliation.id}: {payload.reason}",
            created_by=user.id,
        )
        db.add(movement)
        db.flush()
    reconciliation.status = "RESOLVED"
    reconciliation.resolved_by = user.id
    reconciliation.resolved_at = datetime.now(timezone.utc)
    reconciliation.resolution_reason = payload.reason
    reconciliation.resolution_reference = payload.reference
    reconciliation.adjustment_movement_id = movement.id if movement else None
    db.add(TraceabilityEvent(
        organization_id=user.organization_id,
        lot_number=batch.lot_number,
        event_type="INVENTORY_RECONCILED",
        reference=payload.reference,
        details=f"Reconciliation {reconciliation.id} corrected to {payload.counted_quantity:g} {batch.unit}: {payload.reason}",
    ))
    audit(db, user, "INVENTORY_RECONCILIATION_RESOLVED", "InventoryReconciliation", reconciliation.id, {
        "batch_id": batch.id,
        "previous_on_hand": previous_quantity,
        "ledger_quantity_before": ledger_quantity,
        "counted_quantity": payload.counted_quantity,
        "ledger_adjustment": adjustment_quantity,
        "reference": payload.reference,
        "reason": payload.reason,
    })
    db.commit()
    return {
        **serialize(reconciliation),
        "batch": serialize(batch),
        "adjustment_quantity": adjustment_quantity,
    }


def reserve_materials(db: Session, user: User, order: ProductionOrder):
    if order.material_required <= 0 or not order.material_name:
        return
    batches = db.scalars(select(MaterialBatch).where(MaterialBatch.organization_id == user.organization_id, MaterialBatch.material_name == order.material_name, MaterialBatch.status == "AVAILABLE").order_by(MaterialBatch.received_at.asc()).with_for_update()).all()
    available = sum(max(0, b.quantity_on_hand - b.quantity_reserved) for b in batches)
    if available < order.material_required:
        raise HTTPException(status_code=409, detail=f"Insufficient available stock for {order.material_name}. Available: {available:g}")
    remaining = order.material_required
    reserved_ids = []
    for batch in batches:
        free = max(0, batch.quantity_on_hand - batch.quantity_reserved)
        take = min(free, remaining)
        if take > 0:
            batch.quantity_reserved += take
            reserved_ids.append(f"{batch.id}:{take}")
            db.add(TraceabilityEvent(organization_id=user.organization_id, lot_number=batch.lot_number, event_type="PRODUCTION_RESERVED", reference=order.order_number, details=f"Reserved {take:g} {batch.unit}"))
            remaining -= take
        if remaining <= 0:
            break
    order.reserved_batch_ids = ",".join(reserved_ids)


def release_reservations(db: Session, user: User, order: ProductionOrder, consume: bool = False):
    for item in filter(None, order.reserved_batch_ids.split(",")):
        batch_id_str, amount_str = item.split(":", 1)
        batch = db.scalar(select(MaterialBatch).where(MaterialBatch.id == int(batch_id_str), MaterialBatch.organization_id == user.organization_id).with_for_update())
        amount = float(amount_str)
        if batch:
            if consume and batch.status == "HOLD":
                raise HTTPException(status_code=409, detail=f"Batch {batch.lot_number} is on quality hold and cannot be consumed")
            batch.quantity_reserved = max(0, batch.quantity_reserved - amount)
            if consume:
                if batch.quantity_on_hand < amount:
                    raise HTTPException(status_code=409, detail="Reserved stock no longer exists; contact an administrator")
                batch.quantity_on_hand -= amount
                db.add(InventoryMovement(organization_id=user.organization_id, batch_id=batch.id, movement_type="CONSUMPTION", quantity=-amount, reference=order.order_number, note="Production material consumption", created_by=user.id))
                db.add(TraceabilityEvent(organization_id=user.organization_id, lot_number=batch.lot_number, event_type="PRODUCTION_CONSUMED", reference=order.order_number, details=f"Consumed {amount:g} {batch.unit}"))
    order.reserved_batch_ids = ""


@app.get("/api/v1/production/orders")
def list_production(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if is_supplier_account(user):
        raise HTTPException(status_code=403, detail="Not permitted")
    rows = db.scalars(select(ProductionOrder).where(ProductionOrder.organization_id == user.organization_id).order_by(ProductionOrder.created_at.desc())).all()
    return [serialize(x) for x in rows]


@app.post("/api/v1/production/orders", status_code=201)
def create_production(payload: ProductionCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "PRODUCTION_MANAGER"))):
    if db.scalar(select(ProductionOrder).where(ProductionOrder.organization_id == user.organization_id, ProductionOrder.order_number == payload.order_number)):
        raise HTTPException(status_code=409, detail="Production order number already exists")
    row = ProductionOrder(organization_id=user.organization_id, **payload.model_dump())
    db.add(row); db.flush(); audit(db, user, "CREATE", "ProductionOrder", row.id, {"order_number": row.order_number}); db.commit()
    return serialize(row)


@app.patch("/api/v1/production/orders/{order_id}/status")
def update_production_status(order_id: int, payload: StatusUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "PRODUCTION_MANAGER", "OPERATOR"))):
    order = db.scalar(select(ProductionOrder).where(ProductionOrder.id == order_id, ProductionOrder.organization_id == user.organization_id).with_for_update())
    if not order: raise HTTPException(status_code=404, detail="Production order not found")
    allowed = {"DRAFT": {"PLANNED", "CANCELLED"}, "PLANNED": {"READY", "CANCELLED"}, "READY": {"IN_PROGRESS", "CANCELLED"}, "IN_PROGRESS": {"PAUSED", "COMPLETED", "CANCELLED"}, "PAUSED": {"IN_PROGRESS", "COMPLETED", "CANCELLED"}}
    if payload.status == "CANCELLED" and user.role not in {"ORG_ADMIN", "PRODUCTION_MANAGER"}:
        raise HTTPException(status_code=403, detail="Only an administrator or production manager may cancel an order")
    if payload.status not in allowed.get(order.status, set()):
        raise HTTPException(status_code=409, detail=f"Invalid transition: {order.status} → {payload.status}")
    if payload.status == "READY": reserve_materials(db, user, order)
    if payload.status == "COMPLETED":
        if order.completed_quantity + order.rejected_quantity > order.quantity:
            raise HTTPException(status_code=409, detail="Completed plus rejected quantity cannot exceed order quantity")
        reserved_snapshot = order.reserved_batch_ids
        source_lots = []
        for reserved_item in filter(None, reserved_snapshot.split(",")):
            batch_id_str, _amount_str = reserved_item.split(":", 1)
            source_batch = db.scalar(select(MaterialBatch).where(
                MaterialBatch.id == int(batch_id_str), MaterialBatch.organization_id == user.organization_id
            ))
            if source_batch:
                source_lots.append(source_batch.lot_number)
        if order.track_serials and order.completed_quantity:
            if not float(order.completed_quantity).is_integer():
                raise HTTPException(status_code=422, detail="Serialized finished-product quantity must be a whole number. Disable serial tracking for bulk-measured output.")
            serial_count = int(order.completed_quantity)
            if serial_count > 5000:
                raise HTTPException(status_code=422, detail="A single production order may generate at most 5,000 serial numbers. Split the order into smaller production lots.")
        else:
            serial_count = 0
        release_reservations(db, user, order, consume=True)
        finished_batch = None
        if order.completed_quantity > 0:
            finished_batch = db.scalar(select(FinishedProductBatch).where(
                FinishedProductBatch.organization_id == user.organization_id,
                FinishedProductBatch.production_order_id == order.id,
            ))
            if finished_batch is None:
                finished_batch = FinishedProductBatch(
                    organization_id=user.organization_id,
                    production_order_id=order.id,
                    batch_number=f"FPB-{order.order_number}",
                    product_name=order.product_name,
                    quantity=order.completed_quantity,
                    source_lots_json=json.dumps(sorted(set(source_lots)), ensure_ascii=False),
                )
                db.add(finished_batch)
                db.flush()
        if serial_count:
            existing = db.scalar(select(func.count(FinishedProductSerial.id)).where(
                FinishedProductSerial.organization_id == user.organization_id,
                FinishedProductSerial.production_order_id == order.id,
            )) or 0
            if existing == 0:
                for sequence in range(1, serial_count + 1):
                    serial_number = f"FP-{order.order_number}-{sequence:05d}"
                    db.add(FinishedProductSerial(
                        organization_id=user.organization_id, production_order_id=order.id,
                        finished_product_batch_id=finished_batch.id if finished_batch else None,
                        serial_number=serial_number, product_name=order.product_name,
                        source_lots_json=json.dumps(sorted(set(source_lots)), ensure_ascii=False),
                    ))
                for lot in sorted(set(source_lots)):
                    db.add(TraceabilityEvent(organization_id=user.organization_id, lot_number=lot,
                        event_type="FINISHED_SERIALS_CREATED", reference=order.order_number,
                        details=f"Generated {serial_count} finished-product serials for {order.product_name}"))
                audit(db, user, "SERIALS_GENERATED", "ProductionOrder", order.id,
                    {"count": serial_count, "source_lots": sorted(set(source_lots))})
    if payload.status == "CANCELLED" and order.reserved_batch_ids:
        release_reservations(db, user, order, consume=False)
    order.status = payload.status
    audit(db, user, "STATUS_CHANGE", "ProductionOrder", order.id, {"status": order.status})
    if order.status == "COMPLETED": notify(db, user.organization_id, "Production completed", f"{order.order_number} has been completed.", "SUCCESS")
    db.commit(); return serialize(order)


@app.patch("/api/v1/production/orders/{order_id}/progress")
def update_production_progress(order_id: int, payload: ProductionProgress, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "PRODUCTION_MANAGER", "OPERATOR"))):
    order = db.scalar(select(ProductionOrder).where(ProductionOrder.id == order_id, ProductionOrder.organization_id == user.organization_id).with_for_update())
    if not order: raise HTTPException(status_code=404, detail="Production order not found")
    if order.status not in {"IN_PROGRESS", "PAUSED"}: raise HTTPException(status_code=409, detail="Progress can only be recorded for active or paused orders")
    if payload.completed_quantity + payload.rejected_quantity > order.quantity: raise HTTPException(status_code=422, detail="Completed plus rejected quantity cannot exceed order quantity")
    order.completed_quantity = payload.completed_quantity; order.rejected_quantity = payload.rejected_quantity
    audit(db, user, "PROGRESS_UPDATE", "ProductionOrder", order.id, payload.model_dump()); db.commit(); return serialize(order)


@app.get("/api/v1/quality/templates")
def list_quality_templates(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if is_supplier_account(user): raise HTTPException(status_code=403, detail="Not permitted")
    rows = db.scalars(select(QualityTemplate).where(QualityTemplate.organization_id == user.organization_id, QualityTemplate.is_active.is_(True)).order_by(QualityTemplate.name)).all()
    return [{**serialize(row), "criteria": json.loads(row.criteria_json)} for row in rows]


@app.post("/api/v1/quality/templates", status_code=201)
def create_quality_template(payload: QualityTemplateCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "QUALITY_INSPECTOR"))):
    if db.scalar(select(QualityTemplate).where(QualityTemplate.organization_id == user.organization_id, QualityTemplate.code == payload.code)):
        raise HTTPException(status_code=409, detail="Quality template code already exists")
    row = QualityTemplate(organization_id=user.organization_id, code=payload.code.strip().upper(), name=payload.name.strip(),
        process_type=payload.process_type, criteria_json=json.dumps(payload.criteria, ensure_ascii=False))
    db.add(row); db.flush(); audit(db, user, "CREATE", "QualityTemplate", row.id, {"code": row.code})
    db.commit(); return {**serialize(row), "criteria": payload.criteria}


@app.get("/api/v1/quality/inspections")
def list_inspections(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if is_supplier_account(user): raise HTTPException(status_code=403, detail="Not permitted")
    rows = db.scalars(select(QualityInspection).where(QualityInspection.organization_id == user.organization_id).order_by(QualityInspection.created_at.desc())).all()
    return [{**serialize(x), "criteria_results": json.loads(x.criteria_results_json or "{}"),
             "capa": (lambda c: serialize(c) if c else None)(db.scalar(select(CorrectiveAction).where(CorrectiveAction.inspection_id == x.id, CorrectiveAction.organization_id == user.organization_id)))} for x in rows]


@app.get("/api/v1/quality/finished-batches")
def list_finished_product_batches(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if is_supplier_account(user): raise HTTPException(status_code=403, detail="Not permitted")
    rows = db.scalars(select(FinishedProductBatch).where(
        FinishedProductBatch.organization_id == user.organization_id,
    ).order_by(FinishedProductBatch.created_at.desc())).all()
    return [serialize(row) for row in rows]


@app.get("/api/v1/quality/capa")
def list_corrective_actions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if is_supplier_account(user): raise HTTPException(status_code=403, detail="Not permitted")
    rows = db.scalars(select(CorrectiveAction).where(CorrectiveAction.organization_id == user.organization_id).order_by(CorrectiveAction.created_at.desc())).all()
    return [serialize(x) for x in rows]


@app.patch("/api/v1/quality/capa/{capa_id}")
def update_corrective_action(capa_id: int, payload: CorrectiveActionUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "QUALITY_INSPECTOR", "PRODUCTION_MANAGER"))):
    row = db.scalar(select(CorrectiveAction).where(CorrectiveAction.id == capa_id, CorrectiveAction.organization_id == user.organization_id).with_for_update())
    if not row: raise HTTPException(status_code=404, detail="Corrective-action case not found")
    updates = payload.model_dump(exclude_unset=True)
    requested_status = updates.pop("status", None)
    for key, value in updates.items():
        setattr(row, key, value)
    allowed = {"OPEN": {"CONTAINED"}, "CONTAINED": {"INVESTIGATING"}, "INVESTIGATING": {"IMPLEMENTED"}, "IMPLEMENTED": {"VERIFIED"}, "VERIFIED": {"CLOSED"}, "CLOSED": set()}
    if requested_status and requested_status != row.status:
        if requested_status not in allowed.get(row.status, set()):
            raise HTTPException(status_code=409, detail=f"Invalid CAPA transition: {row.status} → {requested_status}")
        if requested_status == "CONTAINED" and not row.containment_action.strip():
            raise HTTPException(status_code=422, detail="Document the containment action before advancing")
        if requested_status == "INVESTIGATING" and not row.root_cause.strip():
            raise HTTPException(status_code=422, detail="Document the root cause before investigation can advance")
        if requested_status == "IMPLEMENTED" and (not row.corrective_action.strip() or not row.preventive_action.strip()):
            raise HTTPException(status_code=422, detail="Corrective and preventive actions are required before implementation")
        if requested_status == "VERIFIED" and not row.verification.strip():
            raise HTTPException(status_code=422, detail="Verification evidence is required before verification")
        row.status = requested_status
        if requested_status == "CLOSED": row.closed_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    inspection = db.get(QualityInspection, row.inspection_id)
    if row.batch_id:
        batch = db.scalar(select(MaterialBatch).where(MaterialBatch.id == row.batch_id, MaterialBatch.organization_id == user.organization_id))
        if batch:
            db.add(TraceabilityEvent(organization_id=user.organization_id, lot_number=batch.lot_number,
                event_type="CAPA_UPDATED", reference=row.case_number, details=f"Corrective action status: {row.status}"))
    if row.finished_product_batch_id:
        finished_batch = db.scalar(select(FinishedProductBatch).where(
            FinishedProductBatch.id == row.finished_product_batch_id,
            FinishedProductBatch.organization_id == user.organization_id,
        ))
        if finished_batch:
            for lot_number in set(json.loads(finished_batch.source_lots_json or "[]")):
                db.add(TraceabilityEvent(organization_id=user.organization_id, lot_number=lot_number,
                    event_type="CAPA_UPDATED", reference=row.case_number,
                    details=f"Finished-product batch {finished_batch.batch_number}: {row.status}"))
    audit(db, user, "CAPA_UPDATE", "CorrectiveAction", row.id, {"status": row.status, "inspection_id": inspection.id if inspection else None})
    db.commit(); return serialize(row)


@app.post("/api/v1/quality/inspections", status_code=201)
def create_inspection(payload: InspectionCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "QUALITY_INSPECTOR"))):
    result = payload.result.upper()
    if result not in {"PASS", "FAIL"}: raise HTTPException(status_code=422, detail="Result must be PASS or FAIL")
    if db.scalar(select(QualityInspection).where(QualityInspection.organization_id == user.organization_id, QualityInspection.inspection_number == payload.inspection_number)):
        raise HTTPException(status_code=409, detail="Inspection number already exists")
    batch = None
    if payload.batch_id:
        if payload.finished_product_batch_id or payload.finished_product_serial_id:
            raise HTTPException(status_code=422, detail="An inspection cannot target both material and finished-product records")
        batch = db.scalar(select(MaterialBatch).where(MaterialBatch.id == payload.batch_id, MaterialBatch.organization_id == user.organization_id))
        if not batch: raise HTTPException(status_code=404, detail="Batch not found")
    finished_batch = None
    finished_serial = None
    if payload.finished_product_batch_id:
        finished_batch = db.scalar(select(FinishedProductBatch).where(
            FinishedProductBatch.id == payload.finished_product_batch_id,
            FinishedProductBatch.organization_id == user.organization_id,
        ))
        if not finished_batch: raise HTTPException(status_code=404, detail="Finished-product batch not found")
    if payload.finished_product_serial_id:
        finished_serial = db.scalar(select(FinishedProductSerial).where(
            FinishedProductSerial.id == payload.finished_product_serial_id,
            FinishedProductSerial.organization_id == user.organization_id,
        ))
        if not finished_serial: raise HTTPException(status_code=404, detail="Finished-product serial not found")
        serial_batch = db.scalar(select(FinishedProductBatch).where(
            FinishedProductBatch.id == finished_serial.finished_product_batch_id,
            FinishedProductBatch.organization_id == user.organization_id,
        )) if finished_serial.finished_product_batch_id else None
        if not serial_batch:
            raise HTTPException(status_code=409, detail="Finished-product serial has no traceable batch")
        if finished_batch and finished_batch.id != serial_batch.id:
            raise HTTPException(status_code=422, detail="The serial does not belong to the selected finished-product batch")
        finished_batch = serial_batch
    if (finished_batch or finished_serial) and batch:
        raise HTTPException(status_code=422, detail="An inspection cannot target both material and finished-product records")
    product_name = finished_serial.product_name if finished_serial else finished_batch.product_name if finished_batch else payload.product_name
    if (finished_batch or finished_serial) and payload.product_name.strip() != product_name:
        raise HTTPException(status_code=422, detail="Product name must match the selected finished-product record")
    template = None
    criteria_results = payload.criteria_results
    if payload.template_id:
        template = db.scalar(select(QualityTemplate).where(QualityTemplate.id == payload.template_id, QualityTemplate.organization_id == user.organization_id, QualityTemplate.is_active.is_(True)))
        if not template: raise HTTPException(status_code=404, detail="Quality template not found")
        criteria_results, criteria_failed = evaluate_quality_criteria(json.loads(template.criteria_json), payload.criteria_results)
        if criteria_failed: result = "FAIL"
    if result == "PASS" and payload.defect_count > 0:
        raise HTTPException(status_code=422, detail="A passing inspection cannot record defects; use FAIL for non-conforming samples")
    if result == "FAIL" and not payload.corrective_action.strip():
        raise HTTPException(status_code=422, detail="A containment/corrective action is required for failed inspections")
    # Drex is optional advisory routing; it runs before any row is written and
    # its absence or failure never blocks the inspection from being recorded.
    triage = triage_failed_inspection(
        inspection_number=payload.inspection_number,
        product_name=product_name,
        defect_count=payload.defect_count,
        sample_size=payload.sample_size,
        notes=payload.notes,
        containment_action=payload.corrective_action,
        on_hold=bool(batch or finished_batch),
    ) if result == "FAIL" else None
    row = QualityInspection(organization_id=user.organization_id, created_by=user.id, result=result,
        inspection_number=payload.inspection_number, product_name=product_name, batch_id=payload.batch_id,
        finished_product_batch_id=finished_batch.id if finished_batch else None,
        finished_product_serial_id=finished_serial.id if finished_serial else None,
        defect_count=payload.defect_count, sample_size=payload.sample_size, notes=payload.notes,
        corrective_action=payload.corrective_action, template_id=payload.template_id,
        criteria_results_json=json.dumps(criteria_results, ensure_ascii=False))
    db.add(row); db.flush()
    capa = None
    if result == "FAIL":
        capa = CorrectiveAction(organization_id=user.organization_id, inspection_id=row.id, batch_id=batch.id if batch else None,
            finished_product_batch_id=finished_batch.id if finished_batch else None,
            case_number=f"CAPA-{row.inspection_number}", title=f"Corrective action for {row.product_name}",
            status="OPEN", containment_action=payload.corrective_action.strip(), created_by=user.id)
        if triage:
            capa.owner = triage.owner
            notify(db, user.organization_id, "Corrective action routed",
                f"{capa.case_number} was routed to {triage.owner} (Drex confidence {triage.team_probability:.0%}).",
                triage.escalation_level)
        db.add(capa)
        if batch:
            batch.status = "HOLD"
            notify(db, user.organization_id, "Quality hold applied", f"Batch {batch.lot_number} has been placed on hold after a failed inspection.", "CRITICAL")
            db.add(TraceabilityEvent(organization_id=user.organization_id, lot_number=batch.lot_number, event_type="QUALITY_HOLD", reference=row.inspection_number, details=payload.corrective_action))
        if finished_batch:
            finished_batch.status = "HOLD"
            db.execute(
                update(FinishedProductSerial)
                .where(
                    FinishedProductSerial.organization_id == user.organization_id,
                    FinishedProductSerial.finished_product_batch_id == finished_batch.id,
                    FinishedProductSerial.status == "AVAILABLE",
                )
                .values(status="QUARANTINED")
            )
            notify(db, user.organization_id, "Finished-product quality hold applied",
                f"Finished-product batch {finished_batch.batch_number} was quarantined after a failed inspection.", "CRITICAL")
            source_lots = set(json.loads(finished_batch.source_lots_json or "[]"))
            for lot_number in source_lots:
                db.add(TraceabilityEvent(organization_id=user.organization_id, lot_number=lot_number,
                    event_type="FINISHED_QUALITY_HOLD", reference=row.inspection_number,
                    details=f"{finished_batch.batch_number}: {payload.corrective_action}"))
        notify(db, user.organization_id, "Corrective action opened", f"{capa.case_number} was opened for failed inspection {row.inspection_number}.", "WARNING")
    elif batch:
        db.add(TraceabilityEvent(organization_id=user.organization_id, lot_number=batch.lot_number, event_type="QUALITY_PASS", reference=row.inspection_number, details=payload.notes))
    audit(db, user, "CREATE", "QualityInspection", row.id, {"result": result, "template_id": template.id if template else None,
          "triage": ({"team": triage.team, "urgent": triage.urgent, "team_probability": round(triage.team_probability, 4), "request_id": triage.request_id} if triage else None)})
    db.commit()
    return {**serialize(row), "criteria_results": criteria_results, "capa": serialize(capa) if capa else None}


@app.post("/api/v1/quality/batches/{batch_id}/release")
def release_quality_hold(batch_id: int, payload: QualityRelease, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "QUALITY_INSPECTOR"))):
    batch = db.scalar(select(MaterialBatch).where(
        MaterialBatch.id == batch_id,
        MaterialBatch.organization_id == user.organization_id,
    ).with_for_update())
    if not batch:
        raise HTTPException(status_code=404, detail="Material batch not found")
    if batch.status != "HOLD":
        raise HTTPException(status_code=409, detail="Batch is not on quality hold")
    inspection = db.scalar(select(QualityInspection).where(
        QualityInspection.id == payload.inspection_id,
        QualityInspection.organization_id == user.organization_id,
        QualityInspection.batch_id == batch.id,
        QualityInspection.result == "PASS",
    ))
    if not inspection:
        raise HTTPException(status_code=409, detail="A passing inspection for this batch is required")
    latest_inspection = db.scalar(select(QualityInspection).where(
        QualityInspection.organization_id == user.organization_id,
        QualityInspection.batch_id == batch.id,
    ).order_by(QualityInspection.created_at.desc(), QualityInspection.id.desc()).limit(1))
    if not latest_inspection or latest_inspection.id != inspection.id:
        raise HTTPException(status_code=409, detail="The latest inspection must be a passing inspection")
    if not inspection.notes.strip():
        raise HTTPException(status_code=409, detail="Documented passing-inspection notes are required before release")
    reason = payload.reason.strip()
    batch.status = "AVAILABLE"
    db.add(TraceabilityEvent(organization_id=user.organization_id, lot_number=batch.lot_number,
        event_type="QUALITY_RELEASED", reference=inspection.inspection_number, details=reason))
    audit(db, user, "QUALITY_RELEASE", "MaterialBatch", batch.id, {"inspection_id": inspection.id, "reason": reason})
    notify(db, user.organization_id, "Quality hold released", f"Batch {batch.lot_number} was released after passing inspection {inspection.inspection_number}.", "SUCCESS")
    db.commit()
    return serialize(batch)


@app.post("/api/v1/quality/finished-batches/{batch_id}/release")
def release_finished_product_quality_hold(batch_id: int, payload: QualityRelease, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "QUALITY_INSPECTOR"))):
    batch = db.scalar(select(FinishedProductBatch).where(
        FinishedProductBatch.id == batch_id,
        FinishedProductBatch.organization_id == user.organization_id,
    ).with_for_update())
    if not batch:
        raise HTTPException(status_code=404, detail="Finished-product batch not found")
    if batch.status != "HOLD":
        raise HTTPException(status_code=409, detail="Finished-product batch is not on quality hold")
    inspections = db.scalars(select(QualityInspection).where(
        QualityInspection.organization_id == user.organization_id,
        QualityInspection.finished_product_batch_id == batch.id,
    ).order_by(QualityInspection.created_at.desc(), QualityInspection.id.desc())).all()
    latest = inspections[0] if inspections else None
    inspection = next((item for item in inspections if item.id == payload.inspection_id), None)
    if not inspection or inspection.result != "PASS":
        raise HTTPException(status_code=409, detail="A passing inspection for this finished-product batch is required")
    if not latest or latest.id != inspection.id:
        raise HTTPException(status_code=409, detail="The latest batch or serial inspection must be passing")
    if not inspection.notes.strip():
        raise HTTPException(status_code=409, detail="Documented passing-inspection notes are required before release")
    source_lots = set(json.loads(batch.source_lots_json or "[]"))
    held_source_lots = db.scalars(select(MaterialBatch).where(
        MaterialBatch.organization_id == user.organization_id,
        MaterialBatch.lot_number.in_(source_lots),
        MaterialBatch.status == "HOLD",
    )).all() if source_lots else []
    if held_source_lots:
        raise HTTPException(status_code=409, detail="Source material batches must be released before finished-product release")
    batch.status = "AVAILABLE"
    db.execute(
        update(FinishedProductSerial)
        .where(
            FinishedProductSerial.organization_id == user.organization_id,
            FinishedProductSerial.finished_product_batch_id == batch.id,
            FinishedProductSerial.status == "QUARANTINED",
        )
        .values(status="AVAILABLE")
    )
    for lot_number in source_lots:
        db.add(TraceabilityEvent(organization_id=user.organization_id, lot_number=lot_number,
            event_type="FINISHED_QUALITY_RELEASED", reference=inspection.inspection_number,
            details=f"{batch.batch_number}: {payload.reason.strip()}"))
    audit(db, user, "QUALITY_RELEASE", "FinishedProductBatch", batch.id,
        {"inspection_id": inspection.id, "reason": payload.reason.strip()})
    notify(db, user.organization_id, "Finished-product quality hold released",
        f"Finished-product batch {batch.batch_number} was released after passing inspection {inspection.inspection_number}.", "SUCCESS")
    db.commit()
    return serialize(batch)


@app.get("/api/v1/traceability/serials")
def list_finished_serials(status_filter: str | None = Query(default=None, alias="status"), limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if is_supplier_account(user): raise HTTPException(status_code=403, detail="Not permitted")
    query = select(FinishedProductSerial).where(FinishedProductSerial.organization_id == user.organization_id)
    if status_filter: query = query.where(FinishedProductSerial.status == status_filter.upper())
    rows = db.scalars(query.order_by(FinishedProductSerial.created_at.desc()).limit(limit)).all()
    return [serialize(row) for row in rows]


@app.get("/api/v1/traceability/serials/{serial_number}")
def trace_finished_serial(serial_number: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if is_supplier_account(user): raise HTTPException(status_code=403, detail="Not permitted")
    serial = db.scalar(select(FinishedProductSerial).where(FinishedProductSerial.organization_id == user.organization_id, FinishedProductSerial.serial_number == serial_number))
    if not serial: raise HTTPException(status_code=404, detail="Finished-product serial not found")
    order = db.scalar(select(ProductionOrder).where(ProductionOrder.id == serial.production_order_id, ProductionOrder.organization_id == user.organization_id))
    finished_batch = db.scalar(select(FinishedProductBatch).where(
        FinishedProductBatch.id == serial.finished_product_batch_id,
        FinishedProductBatch.organization_id == user.organization_id,
    )) if serial.finished_product_batch_id else None
    finished_inspections = db.scalars(select(QualityInspection).where(
        QualityInspection.organization_id == user.organization_id,
        QualityInspection.finished_product_batch_id == finished_batch.id,
    ).order_by(QualityInspection.created_at)).all() if finished_batch else []
    serial_inspections = db.scalars(select(QualityInspection).where(
        QualityInspection.organization_id == user.organization_id,
        QualityInspection.finished_product_serial_id == serial.id,
    ).order_by(QualityInspection.created_at)).all()
    inspection_by_id = {inspection.id: inspection for inspection in [*finished_inspections, *serial_inspections]}
    finished_capa = db.scalars(select(CorrectiveAction).where(
        CorrectiveAction.organization_id == user.organization_id,
        CorrectiveAction.finished_product_batch_id == finished_batch.id,
    ).order_by(CorrectiveAction.created_at)).all() if finished_batch else []
    lots = json.loads(serial.source_lots_json or "[]")
    sources = []
    for lot in lots:
        batch = db.scalar(select(MaterialBatch).where(MaterialBatch.organization_id == user.organization_id, MaterialBatch.lot_number == lot))
        if not batch: continue
        po = db.get(PurchaseOrder, batch.purchase_order_id) if batch.purchase_order_id else None
        supplier = db.get(Supplier, po.supplier_id) if po else None
        inspections = db.scalars(select(QualityInspection).where(QualityInspection.organization_id == user.organization_id, QualityInspection.batch_id == batch.id).order_by(QualityInspection.created_at)).all()
        sources.append({"batch": serialize(batch), "purchase_order": serialize(po) if po else None,
                        "supplier": serialize(supplier) if supplier else None,
                        "inspections": [serialize(item) for item in inspections]})
    return {"serial": serialize(serial), "production_order": serialize(order) if order else None,
            "finished_product_batch": serialize(finished_batch) if finished_batch else None,
            "finished_product_inspections": [serialize(item) for item in sorted(
                inspection_by_id.values(), key=lambda item: (item.created_at, item.id)
            )],
            "finished_product_corrective_actions": [serialize(item) for item in finished_capa],
            "sources": sources}


@app.patch("/api/v1/traceability/serials/{serial_number}/shipment")
def ship_finished_serial(serial_number: str, payload: SerialShipmentUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "PRODUCTION_MANAGER", "WAREHOUSE_MANAGER"))):
    serial = db.scalar(select(FinishedProductSerial).where(FinishedProductSerial.organization_id == user.organization_id, FinishedProductSerial.serial_number == serial_number).with_for_update())
    if not serial: raise HTTPException(status_code=404, detail="Finished-product serial not found")
    if serial.status != "AVAILABLE": raise HTTPException(status_code=409, detail="Only available finished products can be shipped")
    for lot in json.loads(serial.source_lots_json or "[]"):
        batch = db.scalar(select(MaterialBatch).where(MaterialBatch.organization_id == user.organization_id, MaterialBatch.lot_number == lot))
        if batch and batch.status == "HOLD":
            serial.status = "QUARANTINED"
            db.commit()
            raise HTTPException(status_code=409, detail=f"Source lot {lot} is on quality hold; serial was quarantined")
    serial.status = "SHIPPED"; serial.customer_name = payload.customer_name.strip()
    serial.shipment_reference = payload.shipment_reference.strip(); serial.shipped_at = datetime.now(timezone.utc)
    for lot in json.loads(serial.source_lots_json or "[]"):
        db.add(TraceabilityEvent(organization_id=user.organization_id, lot_number=lot, event_type="FINISHED_PRODUCT_SHIPPED",
            reference=serial.serial_number, details=f"Shipped to {serial.customer_name}; reference {serial.shipment_reference}"))
    audit(db, user, "SHIP", "FinishedProductSerial", serial.id, {"customer_name": serial.customer_name, "shipment_reference": serial.shipment_reference})
    db.commit(); return serialize(serial)


@app.get("/api/v1/traceability/qr/{kind}/{identifier}.svg")
def traceability_qr(kind: str, identifier: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if is_supplier_account(user): raise HTTPException(status_code=403, detail="Not permitted")
    if kind == "lot":
        exists = db.scalar(select(MaterialBatch.id).where(MaterialBatch.organization_id == user.organization_id, MaterialBatch.lot_number == identifier))
    elif kind == "serial":
        exists = db.scalar(select(FinishedProductSerial.id).where(FinishedProductSerial.organization_id == user.organization_id, FinishedProductSerial.serial_number == identifier))
    else:
        raise HTTPException(status_code=422, detail="QR kind must be lot or serial")
    if not exists: raise HTTPException(status_code=404, detail="Traceability identifier not found")
    try:
        import qrcode
        from qrcode.image.svg import SvgPathImage
        qr_payload = f"FACTORYLINK:{kind.upper()}:{identifier}"
        image = qrcode.make(qr_payload, image_factory=SvgPathImage, box_size=8, border=4)
        output = io.BytesIO(); image.save(output)
        return Response(content=output.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "private, no-store"})
    except ImportError:
        raise HTTPException(status_code=503, detail="QR generation dependency is unavailable")


@app.get("/api/v1/traceability/{lot_number}")
def traceability(lot_number: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if is_supplier_account(user): raise HTTPException(status_code=403, detail="Not permitted")
    batch = db.scalar(select(MaterialBatch).where(MaterialBatch.organization_id == user.organization_id, MaterialBatch.lot_number == lot_number))
    if not batch: raise HTTPException(status_code=404, detail="Lot number not found")
    events = db.scalars(select(TraceabilityEvent).where(TraceabilityEvent.organization_id == user.organization_id, TraceabilityEvent.lot_number == lot_number).order_by(TraceabilityEvent.created_at)).all()
    movements = db.scalars(select(InventoryMovement).where(InventoryMovement.organization_id == user.organization_id, InventoryMovement.batch_id == batch.id).order_by(InventoryMovement.created_at)).all()
    order_numbers = {event.reference for event in events if event.event_type in {"PRODUCTION_RESERVED", "PRODUCTION_CONSUMED", "FINISHED_SERIALS_CREATED"}}
    orders = db.scalars(select(ProductionOrder).where(ProductionOrder.organization_id == user.organization_id, ProductionOrder.order_number.in_(order_numbers))).all() if order_numbers else []
    order_ids = [order.id for order in orders]
    serials = db.scalars(select(FinishedProductSerial).where(FinishedProductSerial.organization_id == user.organization_id, FinishedProductSerial.production_order_id.in_(order_ids)).order_by(FinishedProductSerial.serial_number)).all() if order_ids else []
    finished_batches = db.scalars(select(FinishedProductBatch).where(
        FinishedProductBatch.organization_id == user.organization_id,
        FinishedProductBatch.production_order_id.in_(order_ids),
    ).order_by(FinishedProductBatch.batch_number)).all() if order_ids else []
    finished_batch_ids = [item.id for item in finished_batches]
    finished_inspections = db.scalars(select(QualityInspection).where(
        QualityInspection.organization_id == user.organization_id,
        QualityInspection.finished_product_batch_id.in_(finished_batch_ids),
    ).order_by(QualityInspection.created_at)).all() if finished_batch_ids else []
    finished_capas = db.scalars(select(CorrectiveAction).where(
        CorrectiveAction.organization_id == user.organization_id,
        CorrectiveAction.finished_product_batch_id.in_(finished_batch_ids),
    ).order_by(CorrectiveAction.created_at)).all() if finished_batch_ids else []
    po = db.get(PurchaseOrder, batch.purchase_order_id) if batch.purchase_order_id else None
    supplier = db.get(Supplier, po.supplier_id) if po else None
    inspections = db.scalars(select(QualityInspection).where(QualityInspection.organization_id == user.organization_id, QualityInspection.batch_id == batch.id).order_by(QualityInspection.created_at)).all()
    capas = db.scalars(select(CorrectiveAction).where(CorrectiveAction.organization_id == user.organization_id, CorrectiveAction.batch_id == batch.id).order_by(CorrectiveAction.created_at)).all()
    return {"batch": serialize(batch), "purchase_order": serialize(po) if po else None,
            "supplier": serialize(supplier) if supplier else None, "events": [serialize(x) for x in events],
            "movements": [serialize(x) for x in movements], "production_orders": [serialize(x) for x in orders],
            "finished_serials": [serialize(x) for x in serials], "inspections": [serialize(x) for x in inspections],
            "finished_product_batches": [
                {**serialize(finished_batch),
                 "inspections": [serialize(item) for item in finished_inspections if item.finished_product_batch_id == finished_batch.id],
                 "corrective_actions": [serialize(item) for item in finished_capas if item.finished_product_batch_id == finished_batch.id]}
                for finished_batch in finished_batches
            ],
            "corrective_actions": [serialize(x) for x in capas]}


@app.get("/api/v1/maintenance/analytics")
def maintenance_analytics(planned_operating_minutes: int = Query(default=0, ge=0, le=10000000), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if is_supplier_account(user): raise HTTPException(status_code=403, detail="Not permitted")
    equipment = db.scalars(select(Equipment).where(Equipment.organization_id == user.organization_id)).all()
    tasks = db.scalars(select(MaintenanceTask).where(MaintenanceTask.organization_id == user.organization_id)).all()
    preventive = sum(task.downtime_minutes for task in tasks if task.maintenance_type == "PREVENTIVE")
    unplanned = sum(task.downtime_minutes for task in tasks if task.maintenance_type == "UNPLANNED")
    total = preventive + unplanned
    return {"equipment_count": len(equipment), "preventive_downtime_minutes": preventive,
        "unplanned_downtime_minutes": unplanned, "total_downtime_minutes": total,
        "planned_operating_minutes": planned_operating_minutes,
        "availability_percent": round(max(0, planned_operating_minutes - total) / planned_operating_minutes * 100, 2) if planned_operating_minutes else None,
        "availability_note": "Availability is calculated only when the caller supplies planned_operating_minutes for the selected reporting period."}


@app.get("/api/v1/maintenance/equipment")
def list_equipment(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if is_supplier_account(user): raise HTTPException(status_code=403, detail="Not permitted")
    return [serialize(x) for x in db.scalars(select(Equipment).where(Equipment.organization_id == user.organization_id).order_by(Equipment.code)).all()]


@app.post("/api/v1/maintenance/equipment", status_code=201)
def create_equipment(payload: EquipmentCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "MAINTENANCE_MANAGER"))):
    if db.scalar(select(Equipment).where(Equipment.organization_id == user.organization_id, Equipment.code == payload.code)):
        raise HTTPException(status_code=409, detail="Equipment code already exists")
    row = Equipment(organization_id=user.organization_id, **payload.model_dump()); db.add(row); db.flush()
    audit(db, user, "CREATE", "Equipment", row.id, {"code": row.code}); db.commit(); return serialize(row)


@app.get("/api/v1/maintenance/tasks")
def list_maintenance(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if is_supplier_account(user): raise HTTPException(status_code=403, detail="Not permitted")
    rows = db.scalars(select(MaintenanceTask).where(MaintenanceTask.organization_id == user.organization_id).order_by(MaintenanceTask.due_date)).all()
    return [{**serialize(x), "equipment": (db.get(Equipment, x.equipment_id).name if db.get(Equipment, x.equipment_id) else "")} for x in rows]


@app.post("/api/v1/maintenance/tasks", status_code=201)
def create_maintenance(payload: MaintenanceCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "MAINTENANCE_MANAGER"))):
    equipment = db.scalar(select(Equipment).where(Equipment.id == payload.equipment_id, Equipment.organization_id == user.organization_id))
    if not equipment: raise HTTPException(status_code=404, detail="Equipment not found")
    row = MaintenanceTask(organization_id=user.organization_id, **payload.model_dump()); db.add(row); db.flush()
    audit(db, user, "CREATE", "MaintenanceTask", row.id, {"title": row.title}); db.commit(); return serialize(row)


@app.patch("/api/v1/maintenance/tasks/{task_id}")
def update_maintenance(task_id: int, payload: MaintenanceUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "MAINTENANCE_MANAGER"))):
    row = db.scalar(select(MaintenanceTask).where(MaintenanceTask.id == task_id, MaintenanceTask.organization_id == user.organization_id))
    if not row: raise HTTPException(status_code=404, detail="Maintenance task not found")
    if payload.status not in {"SCHEDULED", "IN_PROGRESS", "COMPLETED", "OVERDUE", "CANCELLED"}: raise HTTPException(status_code=422, detail="Invalid maintenance status")
    previous_downtime = row.downtime_minutes
    row.status = payload.status; row.downtime_minutes = payload.downtime_minutes; row.notes = payload.notes
    if payload.maintenance_type is not None: row.maintenance_type = payload.maintenance_type
    equipment = db.get(Equipment, row.equipment_id)
    # Apply only the difference so retrying the same PATCH is idempotent.
    equipment.total_downtime_minutes = max(0, equipment.total_downtime_minutes + payload.downtime_minutes - previous_downtime)
    if payload.status == "COMPLETED" and equipment.status == "MAINTENANCE_DUE": equipment.status = "OPERATIONAL"
    audit(db, user, "UPDATE", "MaintenanceTask", row.id, payload.model_dump()); db.commit(); return serialize(row)


@app.get("/api/v1/notifications")
def list_notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(select(Notification).where(Notification.organization_id == user.organization_id).order_by(Notification.created_at.desc()).limit(50)).all()
    return [serialize(x) for x in rows]


@app.get("/api/v1/notifications/unread-count")
def unread_notification_count(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    count = db.scalar(select(func.count(Notification.id)).where(
        Notification.organization_id == user.organization_id,
        Notification.is_read.is_(False),
    )) or 0
    return {"unread_count": int(count)}


@app.patch("/api/v1/notifications/{notification_id}/read")
def mark_notification_read(notification_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.scalar(select(Notification).where(Notification.id == notification_id, Notification.organization_id == user.organization_id))
    if not row: raise HTTPException(status_code=404, detail="Notification not found")
    row.is_read = True; db.commit(); return serialize(row)


@app.patch("/api/v1/notifications/read-all")
def mark_all_notifications_read(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    result = db.execute(
        update(Notification)
        .where(Notification.organization_id == user.organization_id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    db.commit()
    return {"updated": int(result.rowcount or 0)}


def safe_csv_text(value: str | None) -> str:
    """Prevent spreadsheet applications from evaluating untrusted text as a formula."""
    text = value or ""
    return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text


@app.get("/api/v1/reports/production.csv")
def export_production(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if is_supplier_account(user): raise HTTPException(status_code=403, detail="Not permitted")
    rows = db.scalars(select(ProductionOrder).where(ProductionOrder.organization_id == user.organization_id).order_by(ProductionOrder.order_number)).all()
    buffer = io.StringIO(); writer = csv.writer(buffer)
    writer.writerow(["Order", "Product", "Quantity", "Completed", "Rejected", "Status", "Due date"])
    for r in rows: writer.writerow([safe_csv_text(r.order_number), safe_csv_text(r.product_name), r.quantity, r.completed_quantity, r.rejected_quantity, safe_csv_text(r.status), parse_iso_date(r.due_date)])
    return StreamingResponse(iter(["\ufeff" + buffer.getvalue()]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": "attachment; filename=factorylink-production-report.csv"})


@app.get("/api/v1/reports/production.xlsx")
def export_production_xlsx(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if is_supplier_account(user): raise HTTPException(status_code=403, detail="Not permitted")
    from openpyxl import Workbook
    rows = db.scalars(select(ProductionOrder).where(ProductionOrder.organization_id == user.organization_id).order_by(ProductionOrder.order_number)).all()
    workbook = Workbook(); sheet = workbook.active; sheet.title = "Production"
    sheet.append(["Order", "Product", "Quantity", "Completed", "Rejected", "Status", "Due date"])
    for r in rows:
        sheet.append([safe_csv_text(r.order_number), safe_csv_text(r.product_name), r.quantity, r.completed_quantity, r.rejected_quantity, safe_csv_text(r.status), parse_iso_date(r.due_date)])
        # Explicit string cell types prevent Excel from treating formula-looking text as formulas.
        sheet.cell(row=sheet.max_row, column=1).data_type = "s"
        sheet.cell(row=sheet.max_row, column=2).data_type = "s"
        sheet.cell(row=sheet.max_row, column=6).data_type = "s"
    buffer = io.BytesIO(); workbook.save(buffer); buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=factorylink-production-report.xlsx"})


def _report_workbook(title: str, headers: list[str], rows: list[list], string_columns: set[int] | None = None):
    from openpyxl import Workbook
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title[:31]
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
        for column in (string_columns or set()):
            sheet.cell(row=sheet.max_row, column=column + 1).data_type = "s"
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for column_cells in sheet.columns:
        letter = column_cells[0].column_letter
        max_length = max((len(str(cell.value or "")) for cell in column_cells[:200]), default=10)
        sheet.column_dimensions[letter].width = min(max(max_length + 2, 12), 36)
    return workbook


def _report_csv_response(filename: str, headers: list[str], rows: list[list]):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows(rows)
    return StreamingResponse(iter(["\ufeff" + buffer.getvalue()]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f"attachment; filename={filename}"})


def _report_xlsx_response(filename: str, workbook):
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename={filename}"})


def _ensure_manufacturer_report(user: User):
    if is_supplier_account(user):
        raise HTTPException(status_code=403, detail="Not permitted")


@app.get("/api/v1/reports/inventory.csv")
def export_inventory_csv(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _ensure_manufacturer_report(user)
    rows = db.scalars(select(MaterialBatch).where(MaterialBatch.organization_id == user.organization_id).order_by(MaterialBatch.material_name, MaterialBatch.lot_number)).all()
    headers = ["Material", "Lot number", "On hand", "Reserved", "Available", "Unit", "Unit cost JPY", "Stock value JPY", "Status", "Received at"]
    data = [[safe_csv_text(r.material_name), safe_csv_text(r.lot_number), r.quantity_on_hand, r.quantity_reserved,
             max(0, r.quantity_on_hand - r.quantity_reserved), safe_csv_text(r.unit), r.unit_cost,
             round(r.quantity_on_hand * r.unit_cost, 2), safe_csv_text(r.status), r.received_at.isoformat() if r.received_at else ""] for r in rows]
    return _report_csv_response("factorylink-inventory-report.csv", headers, data)


@app.get("/api/v1/reports/inventory.xlsx")
def export_inventory_xlsx(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _ensure_manufacturer_report(user)
    rows = db.scalars(select(MaterialBatch).where(MaterialBatch.organization_id == user.organization_id).order_by(MaterialBatch.material_name, MaterialBatch.lot_number)).all()
    headers = ["Material", "Lot number", "On hand", "Reserved", "Available", "Unit", "Unit cost JPY", "Stock value JPY", "Status", "Received at"]
    data = [[safe_csv_text(r.material_name), safe_csv_text(r.lot_number), r.quantity_on_hand, r.quantity_reserved,
             max(0, r.quantity_on_hand - r.quantity_reserved), safe_csv_text(r.unit), r.unit_cost,
             round(r.quantity_on_hand * r.unit_cost, 2), safe_csv_text(r.status), r.received_at.isoformat() if r.received_at else ""] for r in rows]
    return _report_xlsx_response("factorylink-inventory-report.xlsx", _report_workbook("Inventory", headers, data, {0, 1, 5, 8}))


@app.get("/api/v1/reports/quality.csv")
def export_quality_csv(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _ensure_manufacturer_report(user)
    rows = db.scalars(select(QualityInspection).where(QualityInspection.organization_id == user.organization_id).order_by(QualityInspection.created_at.desc())).all()
    headers = ["Inspection", "Product", "Lot number", "Result", "Defects", "Sample size", "Defect rate %", "Corrective action", "Inspected at"]
    data = []
    for r in rows:
        batch = db.get(MaterialBatch, r.batch_id) if r.batch_id else None
        data.append([safe_csv_text(r.inspection_number), safe_csv_text(r.product_name), safe_csv_text(batch.lot_number if batch else ""),
                     safe_csv_text(r.result), r.defect_count, r.sample_size, round((r.defect_count / r.sample_size) * 100, 2) if r.sample_size else 0,
                     safe_csv_text(r.corrective_action), r.created_at.isoformat() if r.created_at else ""])
    return _report_csv_response("factorylink-quality-report.csv", headers, data)


@app.get("/api/v1/reports/quality.xlsx")
def export_quality_xlsx(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _ensure_manufacturer_report(user)
    rows = db.scalars(select(QualityInspection).where(QualityInspection.organization_id == user.organization_id).order_by(QualityInspection.created_at.desc())).all()
    headers = ["Inspection", "Product", "Lot number", "Result", "Defects", "Sample size", "Defect rate %", "Corrective action", "Inspected at"]
    data = []
    for r in rows:
        batch = db.get(MaterialBatch, r.batch_id) if r.batch_id else None
        data.append([safe_csv_text(r.inspection_number), safe_csv_text(r.product_name), safe_csv_text(batch.lot_number if batch else ""),
                     safe_csv_text(r.result), r.defect_count, r.sample_size, round((r.defect_count / r.sample_size) * 100, 2) if r.sample_size else 0,
                     safe_csv_text(r.corrective_action), r.created_at.isoformat() if r.created_at else ""])
    return _report_xlsx_response("factorylink-quality-report.xlsx", _report_workbook("Quality", headers, data, {0, 1, 2, 3, 7, 8}))


ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".csv", ".xlsx"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@app.get("/api/v1/documents")
def list_documents(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if is_supplier_account(user):
        supplier_ids = select(Supplier.id).where(Supplier.supplier_organization_id == user.organization_id)
        rows = db.scalars(select(Attachment).where(Attachment.supplier_id.in_(supplier_ids)).order_by(Attachment.created_at.desc())).all()
    else:
        rows = db.scalars(select(Attachment).where(Attachment.organization_id == user.organization_id).order_by(Attachment.created_at.desc())).all()
    return [{"id": x.id, "display_name": x.display_name, "mime_type": x.mime_type, "size_bytes": x.size_bytes, "purchase_order_id": x.purchase_order_id, "created_at": x.created_at.isoformat()} for x in rows]


@app.post("/api/v1/documents", status_code=201)
async def upload_document(file: UploadFile = File(...), purchase_order_id: int | None = Form(default=None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    raw_name = (file.filename or "document").replace("\\", "/")
    original = Path(raw_name).name
    original = "".join(char for char in original if ord(char) >= 32 and ord(char) != 127)[:255] or "document"
    suffix = Path(original).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Allowed file types: PDF, PNG, JPG, CSV, XLSX")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File must be between 1 byte and 10 MB")

    # Do not trust the browser-supplied MIME type; validate the file signature and
    # persist a server-derived MIME type for downloads.
    valid_signature = True
    if suffix == ".pdf":
        valid_signature = content.startswith(b"%PDF-")
    elif suffix == ".png":
        valid_signature = content.startswith(b"\x89PNG\r\n\x1a\n")
    elif suffix in {".jpg", ".jpeg"}:
        valid_signature = content.startswith(b"\xff\xd8\xff")
    elif suffix == ".xlsx":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = set(archive.namelist())
                valid_signature = "[Content_Types].xml" in names and "xl/workbook.xml" in names
        except (zipfile.BadZipFile, OSError):
            valid_signature = False
    elif suffix == ".csv":
        try:
            decoded = content.decode("utf-8-sig")
            valid_signature = "\x00" not in decoded
        except UnicodeDecodeError:
            valid_signature = False
    if not valid_signature:
        raise HTTPException(status_code=415, detail="File content does not match its allowed file type")

    # Antivirus runs before any bytes reach local/S3 persistence. In production
    # startup requires the scanner; scan errors fail closed and do not store data.
    try:
        from starlette.concurrency import run_in_threadpool
        await run_in_threadpool(scan_document_bytes, content)
    except MalwareDetected as exc:
        raise HTTPException(status_code=422, detail="Uploaded document failed malware scanning") from exc
    except MalwareScannerUnavailable as exc:
        access_logger.warning("document_malware_scan_unavailable", extra={"factorylink": {"user_id": user.id}})
        raise HTTPException(status_code=503, detail="Document malware scanning is temporarily unavailable") from exc

    po = None; supplier_id = None; target_org_id = user.organization_id
    if purchase_order_id:
        po = db.get(PurchaseOrder, purchase_order_id)
        if not po: raise HTTPException(status_code=404, detail="Purchase order not found")
        if is_supplier_account(user):
            supplier = db.scalar(select(Supplier).where(Supplier.id == po.supplier_id, Supplier.supplier_organization_id == user.organization_id))
            if not supplier: raise HTTPException(status_code=403, detail="This purchase order is not shared with your supplier account")
            supplier_id = supplier.id; target_org_id = po.organization_id
        elif po.organization_id != user.organization_id:
            raise HTTPException(status_code=403, detail="Purchase order belongs to another organisation")
        else:
            supplier_id = po.supplier_id
    elif is_supplier_account(user):
        raise HTTPException(status_code=422, detail="Supplier documents must be attached to a shared purchase order")
    storage_name = f"{uuid.uuid4().hex}{suffix}"
    mime_type = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".csv": "text/csv", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}[suffix]
    try:
        # Object-store calls are blocking SDK operations; keep them off the
        # async event loop while preserving the existing upload size limit.
        from starlette.concurrency import run_in_threadpool
        await run_in_threadpool(save_document, storage_name, content, mime_type)
    except StorageError as exc:
        raise HTTPException(status_code=503, detail="Document storage is temporarily unavailable") from exc

    row = Attachment(organization_id=target_org_id, purchase_order_id=po.id if po else None, supplier_id=supplier_id,
        uploaded_by=user.id, display_name=original, storage_name=storage_name, mime_type=mime_type, size_bytes=len(content))
    try:
        db.add(row); db.flush(); audit(db, user, "UPLOAD", "Attachment", row.id, {"filename": row.display_name}); db.commit()
    except Exception:
        db.rollback()
        try:
            delete_document(storage_name)
        except StorageError:
            # Keep the original DB exception; an orphan object is recoverable
            # by the periodic object-retention reconciliation job.
            access_logger.exception("document_object_cleanup_failed")
        raise
    return {"id": row.id, "display_name": row.display_name, "mime_type": row.mime_type, "size_bytes": row.size_bytes, "purchase_order_id": row.purchase_order_id, "created_at": row.created_at.isoformat()}


@app.get("/api/v1/documents/{document_id}/download")
def download_document(document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.get(Attachment, document_id)
    if not row: raise HTTPException(status_code=404, detail="Document not found")
    if is_supplier_account(user):
        supplier = db.scalar(select(Supplier).where(Supplier.id == row.supplier_id, Supplier.supplier_organization_id == user.organization_id))
        if not supplier: raise HTTPException(status_code=403, detail="Not permitted")
    elif row.organization_id != user.organization_id:
        raise HTTPException(status_code=403, detail="Not permitted")
    if settings.storage_provider.strip().lower() == "local":
        from pathlib import Path
        path = (Path(settings.upload_dir).expanduser().resolve() / row.storage_name).resolve()
        root = Path(settings.upload_dir).expanduser().resolve()
        if path.parent != root or not path.is_file():
            raise HTTPException(status_code=404, detail="Stored file is missing")
        return FileResponse(
            path,
            media_type=row.mime_type,
            filename=row.display_name,
            headers={
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )
    try:
        content = read_document(row.storage_name)
    except StorageObjectNotFound as exc:
        raise HTTPException(status_code=404, detail="Stored file is missing") from exc
    except StorageError as exc:
        raise HTTPException(status_code=503, detail="Document storage is temporarily unavailable") from exc
    from urllib.parse import quote
    content_disposition = f"attachment; filename*=UTF-8''{quote(row.display_name)}"
    return Response(
        content=content,
        media_type=row.mime_type,
        headers={
            "Content-Disposition": content_disposition,
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/api/v1/audit")
def list_audit(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN"))):
    return [serialize(x) for x in db.scalars(select(AuditLog).where(AuditLog.organization_id == user.organization_id).order_by(AuditLog.created_at.desc()).limit(limit)).all()]

@app.get("/api/v1/organizations/current")
def current_organization(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org = db.get(Organization, user.organization_id)
    return serialize(org)


# ---------------------------------------------------------------------------
# Record maintenance: edit and delete
#
# Operational history is never silently rewritten. These endpoints only allow
# edits while a record is still mutable, block deletes that would orphan
# inventory, quality or financial history, and record every change in the audit
# log. Quality inspections, material lots and stock movements stay immutable by
# design; corrections go through adjustments, rejections and new inspections.
# ---------------------------------------------------------------------------

FACTORY_ROLES = {"ORG_ADMIN", "PRODUCTION_MANAGER", "WAREHOUSE_MANAGER", "QUALITY_INSPECTOR", "MAINTENANCE_MANAGER", "OPERATOR"}


def _locked_org_record(db: Session, model, record_id: int, organization_id: int, label: str):
    row = db.scalar(select(model).where(model.id == record_id, model.organization_id == organization_id).with_for_update())
    if not row:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return row


@app.patch("/api/v1/suppliers/{supplier_id}")
def update_supplier(supplier_id: int, payload: SupplierUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "PRODUCTION_MANAGER"))):
    row = _locked_org_record(db, Supplier, supplier_id, user.organization_id, "Supplier")
    changes = payload.model_dump(exclude_unset=True)
    partner_code = changes.pop("supplier_organization_code", None)
    if changes.get("code"):
        code = str(changes["code"]).strip().upper()
        if db.scalar(select(Supplier.id).where(Supplier.organization_id == user.organization_id, Supplier.code == code, Supplier.id != row.id)):
            raise HTTPException(status_code=409, detail="Supplier code already exists")
        changes["code"] = code
    if partner_code is not None:
        code = str(partner_code).strip().upper()
        if code:
            set_request_context(db, "app.supplier_organization_code", code)
            partner = db.scalar(select(Organization).where(Organization.code == code, Organization.org_type == "SUPPLIER"))
            if not partner:
                raise HTTPException(status_code=404, detail="Supplier organisation code was not found")
            changes["supplier_organization_id"] = partner.id
        else:
            changes["supplier_organization_id"] = None
    for field, value in changes.items():
        setattr(row, field, "" if value is None and field != "supplier_organization_id" else value)
    audit(db, user, "UPDATE", "Supplier", row.id, {key: str(value) for key, value in changes.items()})
    db.commit(); return serialize(row)


@app.delete("/api/v1/suppliers/{supplier_id}", status_code=204)
def delete_supplier(supplier_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "PRODUCTION_MANAGER"))):
    row = _locked_org_record(db, Supplier, supplier_id, user.organization_id, "Supplier")
    if db.scalar(select(PurchaseOrder.id).where(PurchaseOrder.supplier_id == row.id).limit(1)):
        raise HTTPException(status_code=409, detail="This supplier has purchase orders. Cancel them or mark the supplier inactive instead of deleting it.")
    if db.scalar(select(MaterialBatch.id).where(MaterialBatch.supplier_id == row.id).limit(1)):
        raise HTTPException(status_code=409, detail="This supplier is linked to received material lots. Mark the supplier inactive instead of deleting it.")
    if db.scalar(select(Attachment.id).where(Attachment.supplier_id == row.id).limit(1)):
        raise HTTPException(status_code=409, detail="This supplier has shared documents. Delete the documents before deleting the supplier.")
    audit(db, user, "DELETE", "Supplier", row.id, {"code": row.code, "name": row.name})
    db.delete(row); db.commit(); return Response(status_code=204)


@app.patch("/api/v1/purchase-orders/{po_id}")
def update_purchase_order_details(po_id: int, payload: PurchaseOrderUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "PRODUCTION_MANAGER"))):
    row = _locked_org_record(db, PurchaseOrder, po_id, user.organization_id, "Purchase order")
    if row.status not in {"DRAFT", "SUBMITTED"}:
        raise HTTPException(status_code=409, detail="Only draft or submitted purchase orders can be edited")
    changes = payload.model_dump(exclude_unset=True)
    if "po_number" in changes:
        number = str(changes["po_number"]).strip()
        if db.scalar(select(PurchaseOrder.id).where(PurchaseOrder.organization_id == user.organization_id, PurchaseOrder.po_number == number, PurchaseOrder.id != row.id)):
            raise HTTPException(status_code=409, detail="Purchase order number already exists")
        changes["po_number"] = number
    if changes.get("quantity") is not None and float(changes["quantity"]) < float(row.received_quantity or 0):
        raise HTTPException(status_code=409, detail="Ordered quantity cannot be lower than the quantity already received")
    if changes.get("supplier_id") is not None:
        if float(row.received_quantity or 0) > 0:
            raise HTTPException(status_code=409, detail="The supplier cannot change once stock has been received against this order")
        supplier = db.scalar(select(Supplier).where(Supplier.id == changes["supplier_id"], Supplier.organization_id == user.organization_id, Supplier.status == "ACTIVE"))
        if not supplier:
            raise HTTPException(status_code=404, detail="Supplier not found")
    for field, value in changes.items():
        if value is None and field != "due_date":
            continue
        setattr(row, field, value)
    audit(db, user, "UPDATE", "PurchaseOrder", row.id, {key: str(value) for key, value in changes.items()})
    db.commit(); return serialize(row)


@app.delete("/api/v1/purchase-orders/{po_id}", status_code=204)
def delete_purchase_order(po_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "PRODUCTION_MANAGER"))):
    row = _locked_org_record(db, PurchaseOrder, po_id, user.organization_id, "Purchase order")
    if row.status not in {"DRAFT", "CANCELLED"}:
        raise HTTPException(status_code=409, detail="Only draft or cancelled purchase orders can be deleted. Cancel the order first.")
    if db.scalar(select(MaterialBatch.id).where(MaterialBatch.purchase_order_id == row.id).limit(1)):
        raise HTTPException(status_code=409, detail="Stock has been received against this order; it cannot be deleted")
    if db.scalar(select(Attachment.id).where(Attachment.purchase_order_id == row.id).limit(1)):
        raise HTTPException(status_code=409, detail="Shared documents are attached to this order; delete them first")
    audit(db, user, "DELETE", "PurchaseOrder", row.id, {"po_number": row.po_number})
    db.delete(row); db.commit(); return Response(status_code=204)


@app.patch("/api/v1/production/orders/{order_id}")
def update_production_order(order_id: int, payload: ProductionUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "PRODUCTION_MANAGER"))):
    order = _locked_org_record(db, ProductionOrder, order_id, user.organization_id, "Production order")
    if order.status not in {"DRAFT", "PLANNED"}:
        raise HTTPException(status_code=409, detail="Only draft or planned production orders can be edited")
    if float(order.completed_quantity or 0) or float(order.rejected_quantity or 0) or order.reserved_batch_ids:
        raise HTTPException(status_code=409, detail="This order already has recorded output or reserved materials and cannot be edited")
    changes = payload.model_dump(exclude_unset=True)
    if "order_number" in changes:
        number = str(changes["order_number"]).strip()
        if db.scalar(select(ProductionOrder.id).where(ProductionOrder.organization_id == user.organization_id, ProductionOrder.order_number == number, ProductionOrder.id != order.id)):
            raise HTTPException(status_code=409, detail="Production order number already exists")
        changes["order_number"] = number
    if changes.get("track_serials") is not None and db.scalar(select(FinishedProductSerial.id).where(FinishedProductSerial.production_order_id == order.id).limit(1)):
        raise HTTPException(status_code=409, detail="Serial tracking cannot change after serial numbers have been generated")
    for field, value in changes.items():
        if value is None and field != "due_date":
            continue
        setattr(order, field, value)
    audit(db, user, "UPDATE", "ProductionOrder", order.id, {key: str(value) for key, value in changes.items()})
    db.commit(); return serialize(order)


@app.delete("/api/v1/production/orders/{order_id}", status_code=204)
def delete_production_order(order_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "PRODUCTION_MANAGER"))):
    order = _locked_org_record(db, ProductionOrder, order_id, user.organization_id, "Production order")
    if order.status not in {"DRAFT", "PLANNED", "CANCELLED"}:
        raise HTTPException(status_code=409, detail="Only draft, planned or cancelled production orders can be deleted. Cancel an active order first.")
    if db.scalar(select(FinishedProductBatch.id).where(FinishedProductBatch.production_order_id == order.id).limit(1)) or db.scalar(select(FinishedProductSerial.id).where(FinishedProductSerial.production_order_id == order.id).limit(1)):
        raise HTTPException(status_code=409, detail="Finished-product batches or serials were produced from this order; it cannot be deleted")
    if order.reserved_batch_ids:
        release_reservations(db, user, order, consume=False)
    audit(db, user, "DELETE", "ProductionOrder", order.id, {"order_number": order.order_number})
    db.delete(order); db.commit(); return Response(status_code=204)


@app.patch("/api/v1/quality/templates/{template_id}")
def update_quality_template(template_id: int, payload: QualityTemplateUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "QUALITY_INSPECTOR"))):
    row = _locked_org_record(db, QualityTemplate, template_id, user.organization_id, "Quality template")
    changes = payload.model_dump(exclude_unset=True)
    if "criteria" in changes:
        changes["criteria_json"] = json.dumps(changes.pop("criteria") or [], ensure_ascii=False)
    for field, value in changes.items():
        if value is None:
            continue
        setattr(row, field, str(value).strip() if field == "name" else value)
    audit(db, user, "UPDATE", "QualityTemplate", row.id, {"code": row.code})
    db.commit(); return {**serialize(row), "criteria": json.loads(row.criteria_json)}


@app.delete("/api/v1/quality/templates/{template_id}", status_code=204)
def delete_quality_template(template_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "QUALITY_INSPECTOR"))):
    row = _locked_org_record(db, QualityTemplate, template_id, user.organization_id, "Quality template")
    # Inspections reference the applied template, so retire instead of removing.
    row.is_active = False
    audit(db, user, "DELETE", "QualityTemplate", row.id, {"code": row.code, "retired": True})
    db.commit(); return Response(status_code=204)


@app.patch("/api/v1/maintenance/equipment/{equipment_id}")
def update_equipment(equipment_id: int, payload: EquipmentUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "MAINTENANCE_MANAGER"))):
    row = _locked_org_record(db, Equipment, equipment_id, user.organization_id, "Equipment")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("code"):
        code = str(changes["code"]).strip().upper()
        if db.scalar(select(Equipment.id).where(Equipment.organization_id == user.organization_id, Equipment.code == code, Equipment.id != row.id)):
            raise HTTPException(status_code=409, detail="Equipment code already exists")
        changes["code"] = code
    for field, value in changes.items():
        if value is None and field != "next_maintenance":
            continue
        setattr(row, field, value)
    audit(db, user, "UPDATE", "Equipment", row.id, {key: str(value) for key, value in changes.items()})
    db.commit(); return serialize(row)


@app.delete("/api/v1/maintenance/equipment/{equipment_id}", status_code=204)
def delete_equipment(equipment_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "MAINTENANCE_MANAGER"))):
    row = _locked_org_record(db, Equipment, equipment_id, user.organization_id, "Equipment")
    if db.scalar(select(MaintenanceTask.id).where(MaintenanceTask.equipment_id == row.id).limit(1)):
        raise HTTPException(status_code=409, detail="This equipment has maintenance history. Delete its open tasks first or keep the record.")
    audit(db, user, "DELETE", "Equipment", row.id, {"code": row.code})
    db.delete(row); db.commit(); return Response(status_code=204)


@app.patch("/api/v1/maintenance/tasks/{task_id}/details")
def update_maintenance_details(task_id: int, payload: MaintenanceDetailsUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "MAINTENANCE_MANAGER"))):
    task = _locked_org_record(db, MaintenanceTask, task_id, user.organization_id, "Maintenance task")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("equipment_id") is not None and not db.scalar(select(Equipment.id).where(Equipment.id == changes["equipment_id"], Equipment.organization_id == user.organization_id)):
        raise HTTPException(status_code=404, detail="Equipment not found")
    for field, value in changes.items():
        if value is None and field != "due_date":
            continue
        setattr(task, field, value)
    audit(db, user, "UPDATE", "MaintenanceTask", task.id, {key: str(value) for key, value in changes.items()})
    db.commit(); return serialize(task)


@app.delete("/api/v1/maintenance/tasks/{task_id}", status_code=204)
def delete_maintenance_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "MAINTENANCE_MANAGER"))):
    task = _locked_org_record(db, MaintenanceTask, task_id, user.organization_id, "Maintenance task")
    if task.status not in {"SCHEDULED", "CANCELLED"}:
        raise HTTPException(status_code=409, detail="Completed or in-progress maintenance is part of the equipment history and cannot be deleted")
    audit(db, user, "DELETE", "MaintenanceTask", task.id, {"title": task.title})
    db.delete(task); db.commit(); return Response(status_code=204)


@app.patch("/api/v1/users/{user_id}")
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "SUPPLIER_ADMIN"))):
    target = _locked_org_record(db, User, user_id, user.organization_id, "User")
    changes = payload.model_dump(exclude_unset=True)
    if target.id == user.id and ("role" in changes or changes.get("is_active") is False):
        raise HTTPException(status_code=409, detail="You cannot change your own role or deactivate your own account")
    if changes.get("role") is not None:
        organization = db.get(Organization, user.organization_id)
        allowed_roles = FACTORY_ROLES if organization and organization.org_type == "MANUFACTURER" else {"SUPPLIER_USER"}
        if changes["role"] not in allowed_roles:
            raise HTTPException(status_code=422, detail="Role is not valid for this organisation type")
    for field, value in changes.items():
        if value is None:
            continue
        setattr(target, field, value)
    if changes.get("is_active") is False:
        db.execute(update(RefreshToken).where(RefreshToken.user_id == target.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=datetime.now(timezone.utc)))
    audit(db, user, "UPDATE", "User", target.id, {key: str(value) for key, value in changes.items()})
    db.commit(); return {"id": target.id, "email": target.email, "full_name": target.full_name, "role": target.role, "language": target.language, "is_active": target.is_active}


@app.delete("/api/v1/users/{user_id}", status_code=204)
def deactivate_user(user_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("ORG_ADMIN", "SUPPLIER_ADMIN"))):
    target = _locked_org_record(db, User, user_id, user.organization_id, "User")
    if target.id == user.id:
        raise HTTPException(status_code=409, detail="You cannot deactivate your own account")
    # Accounts are deactivated rather than deleted so audit history and records
    # created by the user stay attributable.
    target.is_active = False
    db.execute(update(RefreshToken).where(RefreshToken.user_id == target.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=datetime.now(timezone.utc)))
    audit(db, user, "DEACTIVATE", "User", target.id, {"email": target.email})
    db.commit(); return Response(status_code=204)


@app.delete("/api/v1/documents/{document_id}", status_code=204)
def delete_attachment(document_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.get(Attachment, document_id)
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    if is_supplier_account(user):
        supplier = db.scalar(select(Supplier).where(Supplier.id == row.supplier_id, Supplier.supplier_organization_id == user.organization_id))
        if not supplier:
            raise HTTPException(status_code=403, detail="This document is not shared with your supplier account")
        if row.uploaded_by != user.id and user.role != "SUPPLIER_ADMIN":
            raise HTTPException(status_code=403, detail="Only the uploader or a supplier administrator may delete this document")
    else:
        if row.organization_id != user.organization_id:
            raise HTTPException(status_code=404, detail="Document not found")
        if row.uploaded_by != user.id and user.role not in {"ORG_ADMIN", "PRODUCTION_MANAGER", "WAREHOUSE_MANAGER"}:
            raise HTTPException(status_code=403, detail="Only the uploader or a manager may delete this document")
    try:
        delete_document(row.storage_name)
    except StorageObjectNotFound:
        pass  # The database row is still removed when the object is already gone.
    except StorageError as exc:
        raise HTTPException(status_code=503, detail="Document storage is temporarily unavailable") from exc
    audit(db, user, "DELETE", "Attachment", row.id, {"display_name": row.display_name})
    db.delete(row); db.commit(); return Response(status_code=204)
