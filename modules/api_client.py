"""
Production API находится на сервере университета, а бот запущен на иностранном VPS,
из-за нестабильности сервера университета было принято решение сделать кеширование.
Все HTTP-запросы к API проходят через _fetch_cached. Кеш двухслойный:
- память (_fresh, FRESH_TTL секунд)
- файл (data/cache/) - пишется на каждый успешный ответ,
    но читается только когда сервер не ответил за REQUEST_TIMEOUT или отдал 5xx.

Поддержание кеша актуальным:
- 409 — группа удалена на стороне БГИТУ, файл удаляется сразу;
- изменение расписания - job из modules/groups_cache.py вызывает
    invalidate_lessons() для изменившихся и исчезнувших групп.

teacherSchedule и оба поисковых эндпоинта намеренно не кешируются: слишком
много уникальных ключей.
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Iterable, Optional, Union

import aiohttp
from cachetools import TTLCache

from config_reader import config

logger = logging.getLogger(__name__)

CACHE_DIR = Path("data") / "cache"
LESSONS_DIR = CACHE_DIR / "lessons"
GROUPS_FILE = CACHE_DIR / "groups.json"
REMOTE_CONFIG_FILE = CACHE_DIR / "remote_config.json"

REQUEST_TIMEOUT = 3.0  # секунд на ответ сервера API
FRESH_TTL = 300  # 5 минут в памяти

API_HOST = config.api_host.rstrip('/') + '/'

STATUS_OK = 200
STATUS_TEACHER_NOT_FOUND = 404
STATUS_GROUP_NOT_FOUND = 409
STATUS_UNAVAILABLE = 503

API_UNAVAILABLE_TEXT = "⚠️ Сайт БГИТУ временно недоступен, попробуйте позже"

_fresh: TTLCache = TTLCache(maxsize=4096, ttl=FRESH_TTL)
_inflight: dict[str, asyncio.Future] = {}
_session: Optional[aiohttp.ClientSession] = None


def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            connector=aiohttp.TCPConnector(limit=50, ttl_dns_cache=300),
        )
    return _session


async def close_session() -> None:
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
    _session = None


def _lessons_file(group_id: str) -> Path:
    return LESSONS_DIR / f'{group_id}.json'


def _file_for(kind: str, key: str) -> Path:
    if kind == 'lessons':
        return _lessons_file(key)
    return GROUPS_FILE if kind == 'groups' else REMOTE_CONFIG_FILE


def _write_file(path: Path, data: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f'.{path.name}.tmp')
        tmp_path.write_text(json.dumps(data, ensure_ascii=False), 'utf-8')
        os.replace(tmp_path, path)  # атомарно
    except OSError:
        logger.exception("Не удалось записать файловый кеш %s", path)


def _read_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text('utf-8'))
    except (OSError, ValueError):
        return None


def invalidate_lessons(group_ids: Iterable[Union[int, str]]) -> int:
    """Снести кеш расписания групп из памяти и с диска. Возвращает число снесённых."""
    removed = 0
    for group_id in dict.fromkeys(group_ids):
        key = str(group_id)
        had_in_memory = _fresh.pop(f'lessons:{key}', None) is not None

        try:
            _lessons_file(key).unlink()
            had_on_disk = True
        except FileNotFoundError:
            had_on_disk = False
        except OSError:
            had_on_disk = False
            logger.exception("Не удалось удалить файловый кеш расписания группы %s", key)

        if had_in_memory or had_on_disk:
            removed += 1

    return removed


async def _request(path: str, params: Optional[dict] = None) -> tuple[Optional[int], Any]:
    """Один запрос без кеша. (None, None) - сервер не ответил за REQUEST_TIMEOUT."""
    try:
        async with _get_session().get(API_HOST + path, params=params) as response:
            if response.status != 200:
                return response.status, None
            return response.status, await response.json(content_type=None)
    except (asyncio.TimeoutError, aiohttp.ClientError, ValueError) as e:
        logger.warning("API %s%s недоступен (таймаут %.0fс или ошибка соединения): %s",
                       path, params or '', REQUEST_TIMEOUT, e)
        return None, None


async def _fetch_and_store(cache_key: str, kind: str, key: str, path: str,
                           params: Optional[dict] = None) -> tuple[int, Any]:
    try:
        status, data = await _request(path, params)

        if status == STATUS_OK and data is None:  # 200 без тела
            status = None

        if status == STATUS_OK:
            _fresh[cache_key] = data
            _write_file(_file_for(kind, key), data)
            return status, data

        if status == STATUS_GROUP_NOT_FOUND and kind == 'lessons':
            invalidate_lessons([key])
            return status, None

        if status is not None and status < 500:
            logger.info("API %s%s ответил статусом %s", path, params or '', status)
            return status, None

        stale = _read_file(_file_for(kind, key))
        if stale is not None:
            logger.warning("API %s%s недоступен, отдаём кеш из файла", path, params or '')
            return STATUS_OK, stale

        return STATUS_UNAVAILABLE, None
    finally:
        if cache_key in _inflight:
            del _inflight[cache_key]


async def _fetch_cached(kind: str, key: str, path: str,
                        params: Optional[dict] = None) -> tuple[int, Any]:
    cache_key = f'{kind}:{key}'
    if cache_key in _fresh:
        return STATUS_OK, _fresh[cache_key]

    # один запрос на ключ, параллельные вызовы ждут его
    waiter = _inflight.get(cache_key)
    if waiter is None:
        waiter = asyncio.ensure_future(_fetch_and_store(cache_key, kind, key, path, params))
        _inflight[cache_key] = waiter

    return await asyncio.shield(waiter)


async def get_remote_config() -> dict:
    _, data = await _fetch_cached('remote_config', 'config', 'remoteConfig')
    return data or {}


async def get_groups() -> Optional[list[dict]]:
    _, data = await _fetch_cached('groups', 'all', 'groups')
    return data


async def get_groups_names() -> dict[int, Optional[str]]:
    groups = await get_groups()
    if not groups:
        return {}
    return {group['id']: group.get('name') for group in groups if 'id' in group}


async def get_group_name(group_id: int) -> Optional[str]:
    return (await get_groups_names()).get(group_id)


async def get_schedule(group_id: int) -> tuple[int, Any]:
    return await _fetch_cached('lessons', str(group_id), 'v3/lessons', {'groupId': group_id})


async def get_teacher_schedule(teacher: str) -> tuple[int, Any]:
    status, data = await _request('teacherSchedule', {'teacher': teacher})
    if status != STATUS_OK or data is None:
        return (status or STATUS_UNAVAILABLE), None

    if not any(data.get('first_week', {}).values()) and not any(data.get('second_week', {}).values()):
        return STATUS_TEACHER_NOT_FOUND, None

    return STATUS_OK, data


async def get_teacher_schedule_flat(teacher: str) -> Optional[list[dict]]:
    status, data = await _request('teacherSchedule', {'teacher': teacher, 'teacherSearch': 'true'})
    if status != STATUS_OK or not isinstance(data, list):
        return None
    return data


async def search_groups(query: str) -> Optional[list[dict]]:
    status, data = await _request('groups', {'searchQuery': query})
    return data if status == STATUS_OK and isinstance(data, list) else None


async def search_teachers(query: str) -> Optional[list[str]]:
    status, data = await _request('teacherSchedule', {'searchQuery': query})
    return data if status == STATUS_OK and isinstance(data, list) else None
