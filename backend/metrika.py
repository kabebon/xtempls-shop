"""Клиент Reporting API Яндекс Метрики."""
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

STAT_URL = "https://api-metrika.yandex.net/stat/v1/data"


class MetrikaError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _translate_status(status: int, body: str) -> str:
    if status in (401, 403):
        return "Нет доступа к Метрике: проверьте OAuth-токен и что счётчик принадлежит этому аккаунту Яндекса."
    if status == 404:
        return "Счётчик не найден. Проверьте номер в админке."
    if status == 429:
        return "Метрика временно ограничила запросы. Подождите минуту и обновите."
    text = (body or "").strip()
    if text:
        return f"Метрика вернула ошибку ({status}): {text[:240]}"
    return f"Метрика вернула ошибку ({status})."


async def metrika_query(
    oauth_token: str,
    counter_id: str,
    params: dict,
) -> dict:
    if not oauth_token:
        raise MetrikaError("Сначала сохраните OAuth-токен Метрики в настройках.", 400)
    if not counter_id:
        raise MetrikaError("Укажите номер счётчика Метрики.", 400)
    query = {"ids": counter_id, "accuracy": "full", **params}
    headers = {"Authorization": f"OAuth {oauth_token}"}
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            res = await client.get(STAT_URL, params=query, headers=headers)
    except httpx.HTTPError:
        logger.exception("Metrika request failed")
        raise MetrikaError("Не удалось связаться с API Метрики.", 502)
    if res.status_code >= 400:
        raise MetrikaError(_translate_status(res.status_code, res.text), res.status_code)
    try:
        return res.json()
    except ValueError:
        raise MetrikaError("Метрика вернула некорректный ответ.", 502)


def _rows(payload: dict, dim_count: int) -> list[dict]:
    out = []
    for row in payload.get("data") or []:
        dims = row.get("dimensions") or []
        metrics = row.get("metrics") or []
        item = {}
        for i in range(dim_count):
            cell = dims[i] if i < len(dims) else {}
            item[f"dim{i}"] = (cell or {}).get("name") or "—"
        item["visits"] = int(metrics[0]) if len(metrics) > 0 and metrics[0] is not None else 0
        item["users"] = int(metrics[1]) if len(metrics) > 1 and metrics[1] is not None else 0
        out.append(item)
    return out


async def fetch_overview(oauth_token: str, counter_id: str, date1: str, date2: str) -> dict:
    totals = await metrika_query(oauth_token, counter_id, {
        "date1": date1,
        "date2": date2,
        "metrics": "ym:s:visits,ym:s:users,ym:s:pageviews,ym:s:bounceRate",
    })
    t = (totals.get("totals") or [0, 0, 0, 0])
    links = await metrika_query(oauth_token, counter_id, {
        "date1": date1,
        "date2": date2,
        "metrics": "ym:s:visits,ym:s:users",
        "dimensions": "ym:s:startURL",
        "sort": "-ym:s:visits",
        "limit": 40,
    })
    utm = await metrika_query(oauth_token, counter_id, {
        "date1": date1,
        "date2": date2,
        "metrics": "ym:s:visits,ym:s:users",
        "dimensions": "ym:s:lastSignUTMSource,ym:s:lastSignUTMCampaign",
        "sort": "-ym:s:visits",
        "limit": 40,
    })
    bounce = t[3] if len(t) > 3 and t[3] is not None else 0
    return {
        "visits": int(t[0] or 0),
        "users": int(t[1] or 0) if len(t) > 1 else 0,
        "pageviews": int(t[2] or 0) if len(t) > 2 else 0,
        "bounce_rate": round(float(bounce), 1),
        "links": [
            {"url": r["dim0"], "visits": r["visits"], "users": r["users"]}
            for r in _rows(links, 1)
        ],
        "campaigns": [
            {
                "source": r["dim0"],
                "campaign": r["dim1"],
                "visits": r["visits"],
                "users": r["users"],
            }
            for r in _rows(utm, 2)
        ],
    }
