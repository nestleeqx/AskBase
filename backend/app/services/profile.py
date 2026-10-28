"""Настройки бота: приветствие, тон ответов, контакты для передачи администратору.

Общие настройки клиники меняет владелец. В демо гость меняет свои: они действуют в его
тестовом чате и в его Telegram-чате, подключённом к админке, — у остальных клиентов всё
по-прежнему.
"""

from dataclasses import asdict, dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import CLINIC_OWNER, BotProfile
from app.services.prompts import CLINIC

DEFAULT_GREETING = (
    f"Здравствуйте! Я бот стоматологической клиники «{CLINIC}».\n\n"
    "Отвечаю на вопросы о ценах, врачах, подготовке к процедурам и записи — "
    "по документам клиники. Напишите вопрос своими словами или выберите кнопку внизу."
)


@dataclass
class Profile:
    greeting: str
    tone: str
    phone: str
    hours: str
    # Настройки свои (гостя), а не общие клиники
    custom: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


def default_profile() -> Profile:
    s = get_settings()
    return Profile(
        greeting=DEFAULT_GREETING, tone="neutral", phone=s.clinic_phone, hours=s.clinic_hours
    )


def _from_row(row: BotProfile, custom: bool) -> Profile:
    return Profile(row.greeting, row.tone, row.phone, row.hours, custom)


async def profile_for(session: AsyncSession, visitor: str | None) -> Profile:
    """Свои настройки посетителя, иначе общие настройки клиники, иначе по умолчанию."""
    if visitor:
        row = await session.get(BotProfile, visitor)
        if row is not None:
            return _from_row(row, custom=True)
    row = await session.get(BotProfile, CLINIC_OWNER)
    return _from_row(row, custom=False) if row is not None else default_profile()
