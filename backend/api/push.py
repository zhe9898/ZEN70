import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.core.jwt import get_current_user
from backend.models.user import PushSubscription, User

router = APIRouter()

VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY")
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY")
VAPID_CLAIMS_EMAIL = os.environ.get("VAPID_CLAIMS_EMAIL", "admin@zen70.local")


class PushKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscribeInput(BaseModel):
    endpoint: str
    keys: PushKeys
    user_agent: Optional[str] = None


class PushPayload(BaseModel):
    title: str
    body: str
    icon: Optional[str] = "/pwa-192x192.png"
    url: Optional[str] = "/"


@router.get("/vapid-public-key")
async def get_vapid_public_key():
    """返回供前端 Service Worker 订阅所需 VAPID 公钥"""
    if not VAPID_PUBLIC_KEY:
        raise HTTPException(status_code=503, detail="VAPID keys not configured on server")
    return {"vapid_public_key": VAPID_PUBLIC_KEY}


@router.post("/subscribe", status_code=status.HTTP_201_CREATED)
async def subscribe_push(
    sub_data: PushSubscribeInput,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """将前端通过 pushManager 获取的订阅凭证上报持久化到 Postgres"""

    # Check if endpoint already exists
    existing = await session.execute(
        select(PushSubscription).where(PushSubscription.endpoint == sub_data.endpoint)
    )
    sub = existing.scalar_one_or_none()

    if sub:
        # Update user link and keys if changed
        sub.user_id = current_user.id
        sub.p256dh = sub_data.keys.p256dh
        sub.auth = sub_data.keys.auth
        sub.user_agent = sub_data.user_agent
    else:
        # Insert new subscription
        sub = PushSubscription(
            user_id=current_user.id,
            endpoint=sub_data.endpoint,
            p256dh=sub_data.keys.p256dh,
            auth=sub_data.keys.auth,
            user_agent=sub_data.user_agent,
        )
        session.add(sub)

    await session.commit()
    return {"status": "ok", "message": "Subscription saved successfully"}


@router.post("/test-trigger")
async def test_trigger_push(
    payload: PushPayload,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """(Test) 给当前用户的所有已订阅设备推送原生级别的 Web Push 通知"""
    if not VAPID_PRIVATE_KEY:
        raise HTTPException(status_code=503, detail="VAPID keys not configured")

    res = await session.execute(
        select(PushSubscription).where(PushSubscription.user_id == current_user.id)
    )
    subs = res.scalars().all()

    if not subs:
        raise HTTPException(status_code=404, detail="No push subscriptions found for this user")

    success_count = 0
    fail_count = 0

    for sub in subs:
        sub_info = {"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}
        try:
            # Synchronous block for pywebpush inside async (might want to run in thread for prod)
            webpush(
                subscription_info=sub_info,
                data=payload.model_dump_json(),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": f"mailto:{VAPID_CLAIMS_EMAIL}"},
            )
            success_count += 1
        except WebPushException as ex:
            # Device likely unsubscribed or permission revoked
            fail_count += 1
            if ex.response and ex.response.status_code in [404, 410]:
                await session.delete(sub)  # Clean up dead endpoints

    await session.commit()
    return {"status": "ok", "dispatched": success_count, "failed": fail_count}
