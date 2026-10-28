"""Загрузка страницы сайта по ссылке."""

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

import httpx

from app.services.extract import ExtractError

HTML_TYPES = {"text/html", "application/xhtml+xml"}
USER_AGENT = "Mozilla/5.0 (compatible; AskBaseBot/1.0; knowledge base demo)"
BLOCKED = "Эту ссылку загрузить нельзя: адрес из внутренней сети."


async def _check_host(host: str) -> None:
    """Не пускаем запросы во внутреннюю сеть сервера (localhost, 10.x, 192.168.x и т. п.)."""
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, None)
    except socket.gaierror as e:
        raise ExtractError("Сайт не найден. Проверьте ссылку.") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ExtractError(BLOCKED)


async def fetch_page(url: str, *, allow_private: bool, max_bytes: int) -> tuple[bytes, str]:
    """Содержимое страницы и вид: html или txt."""
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ExtractError("Нужна ссылка на страницу, которая начинается с http:// или https://")

    async def guard(request: httpx.Request) -> None:
        # Проверяется и каждый редирект: внешний сайт может перенаправить во внутреннюю сеть
        if not allow_private:
            await _check_host(request.url.host)

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            follow_redirects=True,
            max_redirects=5,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "ru,en;q=0.8"},
            event_hooks={"request": [guard]},
        ) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code >= 400:
                    raise ExtractError("Страница не открылась. Проверьте, что ссылка рабочая.")
                ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                if ctype not in HTML_TYPES and ctype != "text/plain":
                    raise ExtractError(
                        "По ссылке не веб-страница. Если это файл — скачайте его и загрузите."
                    )
                body = bytearray()
                async for part in resp.aiter_bytes():
                    body += part
                    if len(body) > max_bytes:
                        raise ExtractError("Страница слишком большая для демо.")
    except httpx.HTTPError as e:
        raise ExtractError("Не удалось открыть страницу. Проверьте ссылку.") from e
    return bytes(body), "txt" if ctype == "text/plain" else "html"
