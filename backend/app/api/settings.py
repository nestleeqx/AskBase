from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.deps import SessionDep, Viewer, ViewerDep
from app.models import CLINIC_OWNER, BotProfile, now
from app.services.profile import Profile, default_profile, profile_for
from app.services.prompts import TONES

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ProfileIn(BaseModel):
    greeting: str = Field(min_length=10, max_length=1000)
    tone: Literal["neutral", "friendly", "formal", "brief"]
    phone: str = Field(min_length=5, max_length=40)
    hours: str = Field(min_length=3, max_length=120)


class ProfileOut(ProfileIn):
    # Настройки изменены (у гостя — свои, у владельца — общие настройки клиники)
    custom: bool
    # guest — настройки действуют только у гостя; clinic — для всех клиентов
    scope: Literal["guest", "clinic"]
    defaults: ProfileIn
    tones: dict[str, str]


async def _current(session, viewer: Viewer) -> Profile:
    if not viewer.owner:
        return await profile_for(session, viewer.visitor)
    clinic = await profile_for(session, None)
    clinic.custom = await session.get(BotProfile, CLINIC_OWNER) is not None
    return clinic


async def _drop_own_guest_settings(session, viewer: Viewer) -> None:
    """Владелец меняет общие настройки — его собственные гостевые (из этого же браузера)
    больше не нужны. Иначе в его Telegram-чате, подключённом к админке, они перекрыли бы
    общие, и владелец не увидел бы своих изменений."""
    if not viewer.owner:
        return
    own = await session.get(BotProfile, viewer.visitor)
    if own is not None:
        await session.delete(own)


def _out(profile: Profile, viewer: Viewer) -> ProfileOut:
    d = default_profile()
    return ProfileOut(
        greeting=profile.greeting,
        tone=profile.tone,
        phone=profile.phone,
        hours=profile.hours,
        custom=profile.custom,
        scope="clinic" if viewer.owner else "guest",
        defaults=ProfileIn(greeting=d.greeting, tone=d.tone, phone=d.phone, hours=d.hours),
        tones={key: label for key, (label, _) in TONES.items()},
    )


@router.get("", response_model=ProfileOut)
async def get_profile(session: SessionDep, viewer: ViewerDep):
    return _out(await _current(session, viewer), viewer)


@router.put("", response_model=ProfileOut)
async def save_profile(body: ProfileIn, session: SessionDep, viewer: ViewerDep):
    """Гость меняет свои настройки (его тестовый чат и подключённый Telegram),
    владелец — общие настройки клиники для всех клиентов."""
    row = await session.get(BotProfile, viewer.profile_key)
    if row is None:
        row = BotProfile(owner=viewer.profile_key)
        session.add(row)
    row.greeting = body.greeting.strip()
    row.tone = body.tone
    row.phone = " ".join(body.phone.split())
    row.hours = " ".join(body.hours.split())
    row.updated_at = now()
    await _drop_own_guest_settings(session, viewer)
    await session.commit()
    return _out(await _current(session, viewer), viewer)


@router.delete("", response_model=ProfileOut)
async def reset_profile(session: SessionDep, viewer: ViewerDep):
    """Гость возвращается к общим настройкам клиники, владелец — к настройкам по умолчанию."""
    row = await session.get(BotProfile, viewer.profile_key)
    if row is not None:
        await session.delete(row)
    await _drop_own_guest_settings(session, viewer)
    await session.commit()
    return _out(await _current(session, viewer), viewer)
