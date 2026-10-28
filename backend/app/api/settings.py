from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.deps import SessionDep, VisitorDep
from app.models import BotProfile, now
from app.services.profile import default_profile, profile_for
from app.services.prompts import TONES

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ProfileIn(BaseModel):
    greeting: str = Field(min_length=10, max_length=1000)
    tone: Literal["neutral", "friendly", "formal", "brief"]
    phone: str = Field(min_length=5, max_length=40)
    hours: str = Field(min_length=3, max_length=120)


class ProfileOut(ProfileIn):
    # Свои настройки гостя, а не общие настройки клиники
    custom: bool
    defaults: ProfileIn
    tones: dict[str, str]


def _out(profile) -> ProfileOut:
    d = default_profile()
    return ProfileOut(
        greeting=profile.greeting,
        tone=profile.tone,
        phone=profile.phone,
        hours=profile.hours,
        custom=profile.custom,
        defaults=ProfileIn(greeting=d.greeting, tone=d.tone, phone=d.phone, hours=d.hours),
        tones={key: label for key, (label, _) in TONES.items()},
    )


@router.get("", response_model=ProfileOut)
async def get_profile(session: SessionDep, visitor: VisitorDep):
    return _out(await profile_for(session, visitor))


@router.put("", response_model=ProfileOut)
async def save_profile(body: ProfileIn, session: SessionDep, visitor: VisitorDep):
    """Настройки гостя: действуют в его тестовом чате и подключённом Telegram-чате."""
    row = await session.get(BotProfile, visitor)
    if row is None:
        row = BotProfile(owner=visitor)
        session.add(row)
    row.greeting = body.greeting.strip()
    row.tone = body.tone
    row.phone = " ".join(body.phone.split())
    row.hours = " ".join(body.hours.split())
    row.updated_at = now()
    await session.commit()
    return _out(await profile_for(session, visitor))


@router.delete("", response_model=ProfileOut)
async def reset_profile(session: SessionDep, visitor: VisitorDep):
    """Вернуть настройки по умолчанию — общие настройки клиники."""
    row = await session.get(BotProfile, visitor)
    if row is not None:
        await session.delete(row)
        await session.commit()
    return _out(await profile_for(session, visitor))
