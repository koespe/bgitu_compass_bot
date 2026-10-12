import asyncio
import json
import logging
import urllib.parse
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

import aiohttp
from aiogram import Bot
from bs4 import BeautifulSoup

from config_reader import config

logger = logging.getLogger(__name__)

DATA_DIR = Path("data")
CACHE_FILE = DATA_DIR / "site_updates_data.json"

TARGETS = [
    "https://bgitu.ru/studentu/raspisanie/ochnoe-obuchenie/",
    "https://bgitu.ru/studentu/raspisanie/spo/",
    "https://bgitu.ru/studentu/raspisanie/magistratura/",
]


def parse_links(html_content: str) -> list[str]:
    soup = BeautifulSoup(html_content, "html.parser")
    links = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if href.lower().endswith((".xls", ".xlsx")):
            links.append(urllib.parse.urljoin("https://bgitu.ru", href))
    return links


async def fetch_url(session: aiohttp.ClientSession, url: str) -> Optional[str]:
    try:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.text()
    except Exception as e:
        logger.debug("fetch %s failed: %s", url, e)
    return None


def load_cache() -> set[str]:
    if not CACHE_FILE.exists():
        return set()
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (json.JSONDecodeError, OSError):
        return set()


def save_cache(links: set[str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(links), f, ensure_ascii=False, indent=2)


def filename_from_url(url: str) -> str:
    path = urllib.parse.urlsplit(url).path
    return unquote(path.rsplit("/", 1)[-1])


def build_message_chunk(items: list[str], header: Optional[str] = None) -> str:
    lines = []
    if header:
        lines.append(header)
    for url in items:
        name = filename_from_url(url)
        quoted = urllib.parse.quote(url, safe=":/?&=#")
        lines.append(f'<a href="{quoted}">{name}</a>')
    return "\n".join(lines)


async def collect_links() -> list[str]:
    async with aiohttp.ClientSession() as session:
        all_links: list[str] = []
        for url in TARGETS:
            content = await fetch_url(session, url)
            if not content:
                continue
            all_links.extend(parse_links(content))
        return all_links


async def notify_admin(bot: Bot, new_links: list[str]) -> None:
    header = f"\U0001f4e2 Найдено новых файлов: {len(new_links)}"
    chunk_size = 5
    delay = 1.0
    first = True
    for i in range(0, len(new_links), chunk_size):
        chunk = new_links[i:i + chunk_size]
        text = build_message_chunk(chunk, header=header if first else None)
        await bot.send_message(
            chat_id=config.administration_chat_id,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        first = False
        if i + chunk_size < len(new_links):
            await asyncio.sleep(delay)


async def check_site_updates_and_notify(bot: Bot) -> None:
    """
    Уведомления в административный чат для удобного мониторинга нового расписания
    """
    current_links = await collect_links()
    if not current_links:
        return

    cached = load_cache()
    new_links = [link for link in current_links if link not in cached]

    if new_links:
        await notify_admin(bot, new_links)

    save_cache(set(current_links))


async def main():
    async with aiohttp.ClientSession() as session:
        all_links: list[str] = []
        for url in TARGETS:
            content = await fetch_url(session, url)
            if not content:
                print(f"Не удалось получить {url}")
                continue
            links = parse_links(content)
            if not links:
                print(f"На странице {url} ссылок не найдено")
                continue
            all_links.extend(links)

        if not all_links:
            print("Ссылок не найдено — сайт недоступен/разметка изменилась")
            return

        print(f"Всего найдено ссылок: {len(all_links)}\n")
        for link in all_links:
            print(link)


if __name__ == "__main__":
    asyncio.run(main())
