from __future__ import annotations

import logging
import time
from typing import Callable

import requests

API = "https://api.deezer.com"
USER_AGENT = "music-releases-alert/1.0"
MAX_PAGES = 50

log = logging.getLogger(__name__)


class DeezerError(Exception):
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


class DeezerClient:
    """Small Deezer client. It keeps a minimum gap between all requests."""

    def __init__(
        self,
        delay_ms: int = 200,
        session: requests.Session | None = None,
        timeout: float = 15,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.delay = delay_ms / 1000
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.timeout = timeout
        self._sleep = sleep
        self._clock = clock
        self._last: float | None = None

    def _throttle(self) -> None:
        if self._last is not None:
            wait = self._last + self.delay - self._clock()
            if wait > 0:
                self._sleep(wait)
        self._last = self._clock()

    def _get(self, url: str, params: dict | None = None) -> dict:
        quota_tries = 0
        net_tries = 0
        while True:
            self._throttle()
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                response.raise_for_status()
                data = response.json()
            except (requests.RequestException, ValueError) as exc:
                net_tries += 1
                if net_tries >= 3:
                    raise DeezerError(f"network error: {exc}") from exc
                log.warning("Deezer request failed (%s). Retrying.", exc)
                self._sleep(2 * net_tries)
                continue

            # Deezer reports most errors as HTTP 200 with an "error" object.
            if isinstance(data, dict) and "error" in data:
                err = data["error"]
                code = err.get("code") if isinstance(err, dict) else None
                message = err.get("message") if isinstance(err, dict) else str(err)
                if code == 4 and quota_tries < 3:  # quota limit exceeded
                    quota_tries += 1
                    log.warning("Deezer quota limit hit. Waiting before retry %d.", quota_tries)
                    self._sleep(5 * quota_tries)
                    continue
                raise DeezerError(f"Deezer error {code}: {message}", code)
            return data

    def search_artist(self, query: str) -> list[dict]:
        data = self._get(f"{API}/search/artist", {"q": query, "limit": 10})
        return data.get("data", [])

    def get_artist(self, artist_id: int) -> dict | None:
        try:
            return self._get(f"{API}/artist/{artist_id}")
        except DeezerError as exc:
            if exc.code == 800:  # no data: the artist does not exist
                return None
            raise

    def artist_albums(self, artist_id: int) -> list[dict]:
        url: str | None = f"{API}/artist/{artist_id}/albums"
        params: dict | None = {"limit": 100}
        albums: list[dict] = []
        for _ in range(MAX_PAGES):
            data = self._get(url, params)
            albums.extend(data.get("data", []))
            url = data.get("next")
            params = None
            if not url:
                break
        return albums
