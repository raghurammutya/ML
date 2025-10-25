from __future__ import annotations

from typing import Any, Dict, List

# Placeholder for actual Kite client integration. The production build will
# import `KiteConnect` from `kiteconnect` once credentials are available in the
# environment.


class KiteClient:
    def __init__(self, api_key: str, access_token: str) -> None:
        self.api_key = api_key
        self.access_token = access_token
        # self._kite = KiteConnect(api_key=api_key)
        # self._kite.set_access_token(access_token)

    async def fetch_historical(self, instrument_token: int, from_ts: int, to_ts: int, interval: str) -> List[Dict[str, Any]]:
        # TODO: implement actual API call
        return []

    async def subscribe(self, instrument_tokens: List[int]) -> None:
        # TODO: wire up KiteTicker async callbacks
        pass
