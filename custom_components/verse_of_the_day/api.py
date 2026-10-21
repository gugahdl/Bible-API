"""Small async client for the Bible API this integration reads from.

The data comes from the YouVersion Platform API
(https://developers.youversion.com). This project is an independent,
unofficial client -- not created, endorsed, or affiliated with that company.

This module has no Home Assistant imports on purpose, so it can later move
into its own PyPI package without changes.
"""
from __future__ import annotations

import asyncio
import html as html_lib
import json
import logging
import re
from typing import Any

from aiohttp import ClientError, ClientSession

_LOGGER = logging.getLogger(__name__)

API_BASE_URL = "https://api.youversion.com/v1"
API_KEY_HEADER = "X-YVP-App-Key"
API_USER_AGENT = "HomeAssistant-BibleVerseOfTheDay"

# The documented path is "verse-of-the-days"; the underscore form is what
# earlier releases of this project called. Try the documented one first and
# fall back only on a 404, so either form keeps working.
_VOTD_PATHS = ("/verse-of-the-days", "/verse_of_the_days")

_REQUEST_TIMEOUT = 15
_MAX_PAGES = 20
_PAGE_SIZE = 99

# A DNS blip or a dropped connection is common and self-resolves in seconds;
# retry a couple of times within the same call before giving up.
_RETRY_ATTEMPTS = 3
_RETRY_DELAY = 5  # seconds between attempts

_TAG_RE = re.compile(r"<[^>]+>")


class ApiError(Exception):
    """Base error for anything the API call could not deliver."""


class ApiConnectionError(ApiError):
    """The API could not be reached, timed out, or had a server error."""


class ApiAuthError(ApiError):
    """HTTP 401: the App Key is missing or not recognized."""


class ApiForbiddenError(ApiError):
    """HTTP 403: the App Key is recognized but not allowed to do this.

    Usually the app is archived on the developer portal, or the license for
    that Bible version has not been accepted.
    """


class ApiNotFoundError(ApiError):
    """HTTP 404: the resource or the endpoint path does not exist."""


class ApiRateLimitError(ApiError):
    """HTTP 429: the App Key's request allowance is used up."""

    def __init__(self, retry_after: int | None) -> None:
        """Store the Retry-After value (seconds), when the API sent one."""
        super().__init__(
            f"Rate limit reached; retry after {retry_after}s"
            if retry_after
            else "Rate limit reached"
        )
        self.retry_after = retry_after


def strip_html(raw_html: str | None) -> str:
    """Return a plain-text rendering of an HTML fragment."""
    if not raw_html:
        return ""
    return html_lib.unescape(_TAG_RE.sub("", raw_html)).strip()


def bible_attribution(bible: dict[str, Any]) -> str | None:
    """Return the copyright notice that must be shown with a version's text.

    Mirrors the official SDKs: prefer ``copyright``, fall back to
    ``promotional_content``, and return None when neither has any text.
    """
    for key in ("copyright", "promotional_content"):
        text = strip_html(bible.get(key)).strip().strip('"').strip()
        if text:
            return text
    return None


def _parse_retry_after(value: str | None) -> int | None:
    try:
        return int(value) if value else None
    except ValueError:
        return None


class BibleApiClient:
    """Read-only client for the endpoints this integration uses."""

    def __init__(self, session: ClientSession, app_key: str) -> None:
        """Initialize the client."""
        self._session = session
        self._app_key = app_key
        self._votd_paths = list(_VOTD_PATHS)

    async def _request(
        self, path: str, params: Any = None
    ) -> dict[str, Any] | None:
        """GET ``path`` and return the parsed JSON body (None for HTTP 204).

        Network errors are retried a few times; HTTP errors raise right away
        since retrying with the same key won't help.
        """
        headers = {
            API_KEY_HEADER: self._app_key,
            "Accept": "application/json",
            "User-Agent": API_USER_AGENT,
        }
        last_err: Exception | None = None

        for attempt in range(1, _RETRY_ATTEMPTS + 1):
            try:
                async with asyncio.timeout(_REQUEST_TIMEOUT):
                    async with self._session.get(
                        f"{API_BASE_URL}{path}", headers=headers, params=params
                    ) as resp:
                        status = resp.status
                        body = await resp.text()
                        retry_after = resp.headers.get("Retry-After")
                break
            except (ClientError, TimeoutError) as err:
                last_err = err
                if attempt < _RETRY_ATTEMPTS:
                    _LOGGER.debug(
                        "Request to %s failed (%s); retrying in %ss (%s/%s)",
                        path,
                        err,
                        _RETRY_DELAY,
                        attempt,
                        _RETRY_ATTEMPTS,
                    )
                    await asyncio.sleep(_RETRY_DELAY)
        else:
            raise ApiConnectionError(
                f"Error communicating with the Bible API: {last_err}"
            ) from last_err

        # Check the status before parsing: 204 has no body and 429 is plain
        # text, so neither can be read as JSON.
        if status == 204:
            return None
        if status == 401:
            raise ApiAuthError("The App Key was not recognized (HTTP 401)")
        if status == 403:
            raise ApiForbiddenError(f"Not permitted (HTTP 403): {body[:300]}")
        if status == 404:
            raise ApiNotFoundError(f"Not found (HTTP 404): {path}")
        if status == 429:
            raise ApiRateLimitError(_parse_retry_after(retry_after))
        if status >= 500:
            raise ApiConnectionError(f"Server error (HTTP {status}) for {path}")
        if status >= 400:
            raise ApiError(f"HTTP {status} for {path}: {body[:300]}")

        try:
            data = json.loads(body)
        except ValueError as err:
            raise ApiError(f"Invalid JSON for {path}: {body[:300]}") from err
        if not isinstance(data, dict):
            raise ApiError(f"Unexpected payload for {path}: {body[:300]}")
        return data

    async def async_get_bibles(self, language_range: str) -> list[dict[str, Any]]:
        """Return the Bibles enabled for this App Key in ``language_range``.

        Follows ``next_page_token`` pagination. A language with no versions
        comes back as HTTP 204, which is returned as an empty list.
        """
        bibles: list[dict[str, Any]] = []
        page_token: str | None = None

        for _ in range(_MAX_PAGES):
            params: list[tuple[str, str]] = [
                ("language_ranges[]", language_range),
                ("page_size", str(_PAGE_SIZE)),
            ]
            if page_token:
                params.append(("page_token", page_token))

            body = await self._request("/bibles", params)
            if body is None:
                break
            bibles.extend(body.get("data") or [])
            page_token = body.get("next_page_token")
            if not page_token:
                break

        return bibles

    async def async_get_bible(self, bible_id: int) -> dict[str, Any]:
        """Return one Bible version's metadata (title, copyright, ...)."""
        return await self._request(f"/bibles/{bible_id}") or {}

    async def async_get_verse_of_the_day(self, day: int) -> str:
        """Return the passage id (e.g. ``JHN.3.16``) for a day of the year."""
        last_err: ApiNotFoundError | None = None
        for path in list(self._votd_paths):
            try:
                body = await self._request(f"{path}/{day}")
            except ApiNotFoundError as err:
                last_err = err
                continue
            # Remember the path that worked so later calls go straight to it.
            self._votd_paths = [path]
            passage_id = (body or {}).get("passage_id")
            if not passage_id:
                raise ApiError(f"No passage_id for day {day}: {body}")
            return str(passage_id)
        assert last_err is not None
        raise last_err

    async def async_get_passage(
        self, bible_id: int, passage_id: str, content_format: str = "text"
    ) -> dict[str, Any]:
        """Return a passage in ``content_format`` ("text" or "html")."""
        return (
            await self._request(
                f"/bibles/{bible_id}/passages/{passage_id}",
                {"format": content_format},
            )
            or {}
        )
