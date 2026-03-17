"""
ZEN70 无密码鉴权与 JWT 双轨：WebAuthn 注册/登录、PIN 设置与降级。

路由前缀 /api/v1/webauthn；统一错误码 ZEN-xxx、X-Request-ID、结构化日志。
事务由 get_db 统一 commit/rollback，路由内不显式 commit。
"""

from __future__ import annotations

import json
from typing import Any
import asyncio

import bcrypt
from fastapi import APIRouter, Depends, Request, Response, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.api.deps import get_db, get_redis, get_current_user, get_current_admin
from backend.api.models.auth import (
    BootstrapRequest,
    CreateUserRequest,
    InviteCreateRequest,
    InviteResponse,
    PasswordLoginRequest,
    PinLoginRequest,
    PinSetRequest,
    TokenResponse,
    WebAuthnLoginBeginRequest,
    WebAuthnLoginBeginResponse,
    WebAuthnLoginCompleteRequest,
    WebAuthnRegisterBeginRequest,
    WebAuthnRegisterBeginResponse,
    WebAuthnRegisterCompleteRequest,
)
from backend.core.auth_helpers import (
    CHALLENGE_TTL,
    CODE_BAD_REQUEST,
    CODE_DB_UNAVAILABLE,
    CODE_FORBIDDEN,
    CODE_NOT_FOUND,
    CODE_SERVER_ERROR,
    CODE_TOO_MANY,
    CODE_UNAUTHORIZED,
    check_webauthn_rate_limit,
    consume_challenge,
    credential_id_to_base64url,
    expected_challenge_bytes,
    is_private_ip,
    log_auth,
    origin_from_request,
    require_db_redis,
    request_id,
    client_ip,
    token_response,
    zen,
)
from backend.api.models.auth import AiRoutePreferenceRequest
from backend.core.webauthn import (
    generate_authentication_challenge,
    generate_registration_challenge,
    verify_authentication,
    verify_registration,
)
from backend.models.user import User, WebAuthnCredential
from webauthn.helpers import bytes_to_base64url

from fastapi import status

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

PIN_RATE_LIMIT_KEY = "pin:rate:"
PIN_RATE_LIMIT_MAX = 5
PIN_RATE_LIMIT_WINDOW = 60
BCRYPT_ROUNDS = 12


def _hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


# -------------------- 系统接管 (First-Run) --------------------

@router.get("/sys/status")
async def sys_status(db: AsyncSession | None = Depends(get_db)) -> dict[str, Any]:
    """检查数据库是否有用户。"""
    if db is None:
        raise zen(CODE_DB_UNAVAILABLE, "DB unavailable", status.HTTP_503_SERVICE_UNAVAILABLE)
    result = await db.execute(select(User).limit(1))
    has_user = result.scalar_one_or_none() is not None
    return {"initialized": has_user}


@router.post("/bootstrap", response_model=TokenResponse)
async def bootstrap(
    req: BootstrapRequest,
    db: AsyncSession | None = Depends(get_db),
    redis=Depends(get_redis)
) -> TokenResponse:
    """初始化第一个管理员账户。只有在库为空时可用。"""
    require_db_redis(db, redis)
    result = await db.execute(select(User).limit(1))
    if result.scalar_one_or_none() is not None:
        raise zen(CODE_FORBIDDEN, "System already initialized", status.HTTP_403_FORBIDDEN)
    
    hashed_pw = bcrypt.hashpw(req.password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")
    user = User(
        username=req.username,
        display_name=req.display_name,
        role="admin",
        password_hash=hashed_pw,
        tenant_id="admin_tenant"
    )
    db.add(user)
    await db.flush()
    body = token_response(str(user.id), user.username, user.role)
    return TokenResponse(**body)


# -------------------- 密码直连 --------------------

@router.post("/password/login", response_model=TokenResponse)
async def password_login(
    req: PasswordLoginRequest,
    request: Request,
    db: AsyncSession | None = Depends(get_db),
    redis=Depends(get_redis)
) -> TokenResponse:
    """标准密码登录通道，防爆破，依赖 tenant 和 role。"""
    require_db_redis(db, redis)
    rid, cip = request_id(request), client_ip(request)
    limit_key = f"pwd:rate:{cip}"
    lock_key = f"pwd:lock:{cip}"
    
    # 1. 检查是否已被强制锁定 (15分钟)
    if await redis.get(lock_key):
        log_auth("password_login", False, rid, username=req.username, client_ip_str=cip, detail="hard_locked")
        raise zen(CODE_TOO_MANY, "IP 已被强制锁定，请 15 分钟后再试或联系指挥官解锁", status.HTTP_429_TOO_MANY_REQUESTS)
        
    # 2. 获取当前连续失败次数
    count_str = await redis.get(limit_key)
    fail_count = int(count_str) if count_str else 0
    
    # 3. 指数退避 (法典强制红线: 1次等待1s, 2次5s, 3/4次30s)
    if fail_count == 1:
        await asyncio.sleep(1)
    elif fail_count == 2:
        await asyncio.sleep(5)
    elif fail_count >= 3:
        await asyncio.sleep(30)
        
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()
    
    # 4. 验证密码
    is_valid = False
    if user and user.password_hash:
        if bcrypt.checkpw(req.password.encode("utf-8"), user.password_hash.encode("utf-8")):
            is_valid = True

    if not is_valid:
        # 密码错误 -> 增加失败次数并设置 15 分钟窗口
        new_count = await redis.incr(limit_key)
        if new_count == 1:
            await redis.expire(limit_key, 900)  # 15 分钟记忆窗口
            
        if new_count >= 5:
            await redis.setex(lock_key, 900, "1")  # 强制锁定 15 分钟
            log_auth("password_login", False, rid, username=req.username, client_ip_str=cip, detail="trigger_lock")
            raise zen(CODE_TOO_MANY, "连续失败 5 次，IP 已被锁定 15 分钟", status.HTTP_429_TOO_MANY_REQUESTS)
            
        log_auth("password_login", False, rid, username=req.username, client_ip_str=cip, detail="wrong_password_or_user")
        raise zen(CODE_UNAUTHORIZED, "Invalid credentials", status.HTTP_401_UNAUTHORIZED)
        
    # 5. 验证成功 -> 清除失败记录与锁定
    await redis.delete(limit_key)
    await redis.delete(lock_key)
    
    log_auth("password_login", True, rid, username=req.username, client_ip_str=cip)
    return TokenResponse(**token_response(str(user.id), user.username, user.role))


# -------------------- WebAuthn 注册 --------------------

@router.post("/webauthn/register/begin", response_model=WebAuthnRegisterBeginResponse)
async def register_begin(
    req: WebAuthnRegisterBeginRequest,
    request: Request,
    db: AsyncSession | None = Depends(get_db),
    redis=Depends(get_redis),
) -> WebAuthnRegisterBeginResponse:
    require_db_redis(db, redis)
    rid, cip = request_id(request), client_ip(request)
    await check_webauthn_rate_limit(redis, cip, rid)

    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()
    if not user:
        user = User(username=req.username, display_name=req.display_name or req.username)
        db.add(user)
        await db.flush()
    user_id_bytes = str(user.id).encode("utf-8")

    _, challenge_b64, options_json_str = generate_registration_challenge(
        username=req.username,
        display_name=req.display_name or req.username,
        user_id=user_id_bytes,
    )
    options_dict = json.loads(options_json_str)
    payload = json.dumps({"user_id": user.id, "username": user.username, "flow": "register"})
    if not await redis.set_auth_challenge(challenge_b64, payload, ttl=CHALLENGE_TTL):
        raise zen(CODE_SERVER_ERROR, "Failed to store challenge", status.HTTP_500_INTERNAL_SERVER_ERROR)

    log_auth("webauthn_register_begin", True, rid, username=req.username, client_ip_str=cip)
    return WebAuthnRegisterBeginResponse(options=options_dict)


@router.post("/webauthn/register/complete")
async def register_complete(
    req: WebAuthnRegisterCompleteRequest,
    request: Request,
    db: AsyncSession | None = Depends(get_db),
    redis=Depends(get_redis),
) -> dict[str, str]:
    require_db_redis(db, redis)
    rid, cip = request_id(request), client_ip(request)
    await check_webauthn_rate_limit(redis, cip, rid)

    challenge_b64, data = await consume_challenge(redis, req.credential, "register", username=None)
    user_id = data.get("user_id")
    username = data.get("username")
    if user_id is None or not username:
        raise zen(CODE_BAD_REQUEST, "Invalid challenge data", status.HTTP_400_BAD_REQUEST)

    origin = origin_from_request(request)
    try:
        verification = verify_registration(
            credential=req.credential,
            expected_challenge=expected_challenge_bytes(challenge_b64),
            origin=origin,
        )
    except Exception as e:
        log_auth("webauthn_register_complete", False, rid, username=username, detail=str(e))
        raise zen(CODE_BAD_REQUEST, "Registration verification failed", status.HTTP_400_BAD_REQUEST)

    credential_id_b64 = bytes_to_base64url(verification.credential_id)
    device_name = (req.credential.get("deviceName") or (req.credential.get("response") or {}).get("deviceName") or "unknown")[:128]
    cred = WebAuthnCredential(
        user_id=int(user_id),
        credential_id=credential_id_b64,
        public_key=verification.credential_public_key,
        sign_count=verification.sign_count,
        device_name=device_name,
    )
    db.add(cred)
    log_auth("webauthn_register_complete", True, rid, username=username, client_ip_str=cip)
    return {"status": "ok", "message": "Credential registered"}


# -------------------- 登录 --------------------


@router.post("/webauthn/login/begin", response_model=WebAuthnLoginBeginResponse)
async def login_begin(
    req: WebAuthnLoginBeginRequest,
    request: Request,
    db: AsyncSession | None = Depends(get_db),
    redis=Depends(get_redis),
) -> WebAuthnLoginBeginResponse:
    require_db_redis(db, redis)
    rid, cip = request_id(request), client_ip(request)
    await check_webauthn_rate_limit(redis, cip, rid)

    result = await db.execute(
        select(User).where(User.username == req.username).options(selectinload(User.credentials))
    )
    user = result.scalar_one_or_none()
    if not user:
        log_auth("webauthn_login_begin", False, rid, username=req.username, detail="user_not_found")
        raise zen(CODE_NOT_FOUND, "User not found", status.HTTP_404_NOT_FOUND)
    creds = list(user.credentials)
    if not creds:
        log_auth("webauthn_login_begin", False, rid, username=req.username, detail="no_credentials")
        raise zen(CODE_NOT_FOUND, "No credentials found for user", status.HTTP_404_NOT_FOUND)

    allow_credentials = [
        {"id": c.credential_id, "type": "public-key", "transports": ["internal", "usb", "nfc"]}
        for c in creds
    ]
    _, challenge_b64, options_json_str = generate_authentication_challenge(allow_credentials=allow_credentials)
    options_dict = json.loads(options_json_str)
    payload = json.dumps({"user_id": user.id, "username": user.username, "flow": "login"})
    if not await redis.set_auth_challenge(challenge_b64, payload, ttl=CHALLENGE_TTL):
        raise zen(CODE_SERVER_ERROR, "Failed to store challenge", status.HTTP_500_INTERNAL_SERVER_ERROR)

    log_auth("webauthn_login_begin", True, rid, username=req.username, client_ip_str=cip)
    return WebAuthnLoginBeginResponse(options=options_dict)


@router.post("/webauthn/login/complete", response_model=TokenResponse)
async def login_complete(
    req: WebAuthnLoginCompleteRequest,
    request: Request,
    response: Response,
    db: AsyncSession | None = Depends(get_db),
    redis=Depends(get_redis),
) -> TokenResponse:
    require_db_redis(db, redis)
    rid, cip = request_id(request), client_ip(request)
    await check_webauthn_rate_limit(redis, cip, rid)

    challenge_b64, data = await consume_challenge(redis, req.credential, "login", username=req.username)
    cred_id_b64 = credential_id_to_base64url(req.credential)
    if not cred_id_b64:
        raise zen(CODE_BAD_REQUEST, "Invalid credential: missing id", status.HTTP_400_BAD_REQUEST)

    cred_result = await db.execute(
        select(WebAuthnCredential).where(
            WebAuthnCredential.credential_id == cred_id_b64,
            WebAuthnCredential.user_id == int(data["user_id"]),
        )
    )
    cred = cred_result.scalar_one_or_none()
    if not cred:
        log_auth("webauthn_login_complete", False, rid, username=req.username, detail="credential_not_found")
        raise zen(CODE_NOT_FOUND, "Credential not found", status.HTTP_404_NOT_FOUND)

    origin = origin_from_request(request)
    try:
        verification = verify_authentication(
            credential=req.credential,
            expected_challenge=expected_challenge_bytes(challenge_b64),
            origin=origin,
            credential_public_key=cred.public_key,
            credential_current_sign_count=cred.sign_count,
        )
    except Exception as e:
        log_auth("webauthn_login_complete", False, rid, username=req.username, detail=str(e))
        raise zen(CODE_BAD_REQUEST, "Authentication verification failed", status.HTTP_400_BAD_REQUEST)

    cred.sign_count = verification.new_sign_count
    body = token_response(str(cred.user_id), req.username, "user")
    log_auth("webauthn_login_complete", True, rid, username=req.username, client_ip_str=cip)
    return TokenResponse(**body)


# -------------------- PIN 降级与设置 --------------------


@router.post("/pin/login", response_model=TokenResponse)
async def pin_login(
    req: PinLoginRequest,
    request: Request,
    db: AsyncSession | None = Depends(get_db),
    redis=Depends(get_redis),
) -> TokenResponse:
    require_db_redis(db, redis)
    rid, cip = request_id(request), client_ip(request)

    if not is_private_ip(cip):
        log_auth("pin_login", False, rid, username=req.username, client_ip_str=cip, detail="not_private_ip")
        raise zen(CODE_FORBIDDEN, "PIN login only allowed from local network", status.HTTP_403_FORBIDDEN)

    freeze_key = f"pin:freeze:{cip}"
    if await redis.get(freeze_key):
        raise zen(CODE_TOO_MANY, "错误次数过多，已被防爆破大闸冻结 60 秒", status.HTTP_429_TOO_MANY_REQUESTS)

    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar_one_or_none()
    
    async def _handle_failure(detail: str):
        count = await redis.incr_with_expire(f"{PIN_RATE_LIMIT_KEY}{cip}", PIN_RATE_LIMIT_WINDOW)
        if count >= PIN_RATE_LIMIT_MAX:
             await redis.setex(freeze_key, PIN_RATE_LIMIT_WINDOW, "1")
             log_auth("pin_login", False, rid, username=req.username, client_ip_str=cip, detail="trigger_lock")
             raise zen(CODE_TOO_MANY, f"连续失败 {PIN_RATE_LIMIT_MAX} 次，已触发 60 秒锁定防爆破", status.HTTP_429_TOO_MANY_REQUESTS)
        log_auth("pin_login", False, rid, username=req.username, client_ip_str=cip, detail=detail)
        raise zen(CODE_UNAUTHORIZED, "Invalid credentials", status.HTTP_401_UNAUTHORIZED)
        
    if not user or not user.pin_hash:
        await _handle_failure("invalid_user_or_no_pin")

    pin_bytes = req.pin.encode("utf-8")
    pin_hash_bytes = user.pin_hash.encode("utf-8") if isinstance(user.pin_hash, str) else user.pin_hash
    if not bcrypt.checkpw(pin_bytes, pin_hash_bytes):
        await _handle_failure("wrong_pin")

    await redis.delete(f"{PIN_RATE_LIMIT_KEY}{cip}")
    await redis.delete(freeze_key)
    
    log_auth("pin_login", True, rid, username=req.username, client_ip_str=cip)
    return TokenResponse(**token_response(str(user.id), user.username, "family"))


@router.post("/pin/set")
async def pin_set(
    req: PinSetRequest,
    request: Request,
    db: AsyncSession | None = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, str]:
    """设置或修改当前用户 PIN（需已登录；若账户已有 PIN 则需提供 pin_old）。"""
    if db is None:
        raise zen(CODE_DB_UNAVAILABLE, "Database not configured", status.HTTP_503_SERVICE_UNAVAILABLE)
    rid, cip = request_id(request), client_ip(request)
    username = current_user.get("username")
    if not username:
        raise zen(CODE_UNAUTHORIZED, "Invalid token payload", status.HTTP_401_UNAUTHORIZED)

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise zen(CODE_NOT_FOUND, "User not found", status.HTTP_404_NOT_FOUND)

    if user.pin_hash:
        if not req.pin_old:
            raise zen(CODE_BAD_REQUEST, "pin_old required when changing PIN", status.HTTP_400_BAD_REQUEST)
        pin_old_bytes = req.pin_old.encode("utf-8")
        hash_bytes = user.pin_hash.encode("utf-8") if isinstance(user.pin_hash, str) else user.pin_hash
        if not bcrypt.checkpw(pin_old_bytes, hash_bytes):
            log_auth("pin_set", False, rid, username=username, client_ip_str=cip, detail="wrong_pin_old")
            raise zen(CODE_UNAUTHORIZED, "Invalid pin_old", status.HTTP_401_UNAUTHORIZED)

    user.pin_hash = _hash_pin(req.pin_new)
    log_auth("pin_set", True, rid, username=username, client_ip_str=cip)
    return {"status": "ok", "message": "PIN updated"}


# -------------------- 账号管理 (Admin) --------------------

@router.patch("/me/ai-preference", response_model=TokenResponse)
async def update_ai_preference(
    req: AiRoutePreferenceRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> TokenResponse:
    """法典 M9.4: 调整用户的 AI 计算偏好，并在此刻立刻颁发新 JWT 使配置 0 延迟生效。"""
    if req.preference not in ("local", "cloud", "auto"):
        raise zen(CODE_BAD_REQUEST, "Invalid preference value", status.HTTP_400_BAD_REQUEST)
        
    username = current_user.get("username")
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise zen(CODE_NOT_FOUND, "User not found", status.HTTP_404_NOT_FOUND)
        
    user.ai_route_preference = req.preference
    await db.flush()
    log_auth("ai_preference_update", True, request_id(request), username=username, detail=f"changed_to_{req.preference}")
    
    # 物理颁发新 JWT 供网关 ai_router 解码截获
    body = token_response(
        sub=str(user.id), 
        username=user.username, 
        role=user.role, 
        tenant_id=user.tenant_id,
        ai_route_preference=user.ai_route_preference
    )
    return TokenResponse(**body)



@router.get("/users", response_model=UserListResponse)
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
) -> UserListResponse:
    """列出所有系统用户及其 WebAuthn 设备"""
    result = await db.execute(select(User).options(selectinload(User.credentials)))
    users = result.scalars().all()
    
    user_items = []
    for u in users:
        creds = [{"id": c.credential_id, "name": c.device_name, "created_at": str(c.created_at)} for c in u.credentials]
        user_items.append(UserItem(
            id=u.id,
            username=u.username,
            display_name=u.display_name,
            role=u.role,
            tenant_id=u.tenant_id,
            is_active=u.is_active,
            has_password=bool(u.password_hash),
            webauthn_credentials=creds
        ))
    return UserListResponse(users=user_items)


@router.post("/users", response_model=UserItem)
async def create_user(
    req: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
) -> UserItem:
    """管理员强制后台创建账号"""
    result = await db.execute(select(User).where(User.username == req.username))
    if result.scalar_one_or_none():
        raise zen(CODE_BAD_REQUEST, "Username already exists", status.HTTP_400_BAD_REQUEST)
        
    hashed_pw = bcrypt.hashpw(req.password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")
    user = User(
        username=req.username,
        display_name=req.display_name,
        role=req.role,
        password_hash=hashed_pw,
        tenant_id=req.tenant_id
    )
    db.add(user)
    await db.flush()
    
    return UserItem(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        tenant_id=user.tenant_id,
        is_active=user.is_active,
        has_password=True,
        webauthn_credentials=[]
    )


@router.delete("/credentials/{credential_id}")
async def revoke_credential(
    credential_id: str,
    db: AsyncSession = Depends(get_db),
    current_admin: dict = Depends(get_current_admin)
) -> dict[str, str]:
    """吊销（删除）某个指纹/面容设备凭证防丢"""
    result = await db.execute(select(WebAuthnCredential).where(WebAuthnCredential.credential_id == credential_id))
    cred = result.scalar_one_or_none()
    if not cred:
        raise zen(CODE_NOT_FOUND, "Credential not found", status.HTTP_404_NOT_FOUND)
        
    await db.delete(cred)
    await db.flush()
    return {"status": "ok", "message": "Credential revoked successfully"}

# -------------------- OOB 邀请系统 (Invite System) --------------------

import secrets
import time

INVITE_TOKEN_PREFIX = "zen70:invite:"

@router.post("/invites", response_model=InviteResponse)
async def create_invite(
    req: InviteCreateRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    current_admin: dict = Depends(get_current_admin)
) -> InviteResponse:
    """生成一次性邀请凭证（仅管理员可用）"""
    require_db_redis(db, redis)
    
    # 验证用户是否存在
    result = await db.execute(select(User).where(User.id == req.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise zen(CODE_NOT_FOUND, "User not found", status.HTTP_404_NOT_FOUND)
        
    # 生成高强度随机 Token (32 字节 hex)
    token = secrets.token_hex(32)
    expires_in = req.expires_in_minutes * 60
    
    # 存入 Redis，物理设置过期时间
    token_key = f"{INVITE_TOKEN_PREFIX}{token}"
    token_data = json.dumps({"user_id": user.id})
    await redis.setex(token_key, expires_in, token_data)
    
    expires_at = int(time.time()) + expires_in
    return InviteResponse(token=token, expires_at=expires_at)


@router.post("/invites/{token}/webauthn/register/begin", response_model=WebAuthnRegisterBeginResponse)
async def invite_webauthn_register_begin(
    token: str,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis)
) -> WebAuthnRegisterBeginResponse:
    """带外传递链接 - 开始注册 WebAuthn"""
    require_db_redis(db, redis)
    
    token_key = f"{INVITE_TOKEN_PREFIX}{token}"
    token_data_str = await redis.get(token_key)
    if not token_data_str:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="凭证已失效或不存在"
        )
        
    token_data = json.loads(token_data_str)
    user_id = token_data["user_id"]
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="绑定用户不存在")
        
    registration_data, state = generate_registration_challenge(user.username, user.display_name or user.username)
    
    # 存储 Challenge (使用原有的 CHALLENGE_TTL 逻辑，但为了方便与当前操作关联，使用 user_id 键)
    challenge_key = f"webauthn:reg:{user.username}"
    # Python 字典转 JSON 存 Redis
    state["user_id"] = user.id  # 附加 ID 后续比对
    await redis.setex(challenge_key, CHALLENGE_TTL, json.dumps(state))
    
    return WebAuthnRegisterBeginResponse(options=json.loads(registration_data))


@router.post("/invites/{token}/webauthn/register/complete")
async def invite_webauthn_register_complete(
    token: str,
    req: WebAuthnRegisterCompleteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis)
) -> dict[str, Any]:
    """带外传递链接 - 完成 WebAuthn 注册并销毁 Token"""
    require_db_redis(db, redis)
    
    # 1. 验证 Token 是否还有效
    token_key = f"{INVITE_TOKEN_PREFIX}{token}"
    token_data_str = await redis.get(token_key)
    if not token_data_str:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="凭证已失效或不存在"
        )
    
    token_data = json.loads(token_data_str)
    user_id = token_data["user_id"]
    
    # 2. 获取用户
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="绑定用户不存在")
        
    # 3. 获取 Challenge
    challenge_key = f"webauthn:reg:{user.username}"
    state_str = await consume_challenge(redis, challenge_key)
    state = json.loads(state_str)
    expected_challenge = expected_challenge_bytes(state["challenge"])
    
    # 4. 验证 WebAuthn 凭据
    origin = origin_from_request(request)
    try:
        verification = verify_registration(
            credential=req.credential,
            expected_challenge=expected_challenge,
            expected_origin=origin,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"WebAuthn verification failed: {str(e)}")
        
    # 5. 存储新生成的硬件证书公钥 (物理绑定)
    cred_id_str = credential_id_to_base64url(verification.credential_id)
    new_cred = WebAuthnCredential(
        user_id=user.id,
        credential_id=cred_id_str,
        public_key=verification.credential_public_key,
        sign_count=verification.sign_count,
        device_name=str(req.credential.get("id", "zen70-bound-device")), # 简单存个ID或未知
    )
    db.add(new_cred)
    await db.flush()
    
    # 6. 一旦绑定成功，【物理熔断】(删除) 这个凭证 Token，保证 100% 一次性
    await redis.delete(token_key)
    
    # 注册成功后可直接踢给用户一个有效 JWT (可选，此处直接下发)
    access_token = token_response(user.id, user.username, user.role, request_id(request), user.tenant_id)
    return {
        "status": "ok", 
        "message": "物理绑定完成，Token已销毁",
        "access_token": access_token.access_token,
        "token_type": access_token.token_type
    }

@router.post("/invites/{token}/fallback/login")
async def invite_fallback_login(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis)
) -> dict[str, Any]:
    """带外传递链接 - 大陆安卓设备降级免密直连并销毁 Token"""
    require_db_redis(db, redis)
    
    # 1. 验证 Token 是否还有效
    token_key = f"{INVITE_TOKEN_PREFIX}{token}"
    token_data_str = await redis.get(token_key)
    if not token_data_str:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="凭证已失效或不存在"
        )
    
    token_data = json.loads(token_data_str)
    user_id = token_data["user_id"]
    
    # 2. 获取用户
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="绑定用户不存在")
        
    # 3. 降级模式：不进行物理绑定，直接放行并销毁凭证
    await redis.delete(token_key)
    
    access_token = token_response(user.id, user.username, user.role, request_id(request), user.tenant_id)
    return {
        "status": "ok", 
        "message": "免密登入成功 (降级模式)，Token已销毁",
        "access_token": access_token.access_token,
        "token_type": access_token.token_type
    }
