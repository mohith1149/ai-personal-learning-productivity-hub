"""One place for the provider adapters' HTTP POST: retry a connection that could not be established, and explain failures safely.

A ConnectError means no connection was made, so nothing was sent and a retry cannot run a request twice. Seen in practice: on a machine whose
antivirus or proxy intermittently re-signs HTTPS traffic, about one connection in three fails certificate verification and the next one works.
Certificate checking is NEVER switched off. If it keeps failing, the message says what to look at."""
import time

import httpx

from app.ai.types import ProviderError

ATTEMPTS = 3
PAUSE = 0.4  # seconds, multiplied by the attempt number


def post(http: httpx.Client, url: str, provider: str, **kwargs) -> httpx.Response:
    last: httpx.ConnectError | None = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return http.post(url, **kwargs)
        except httpx.ConnectError as e:
            last = e
            if attempt < ATTEMPTS:
                time.sleep(PAUSE * attempt)
        except httpx.HTTPError:
            raise ProviderError(f"Couldn't reach the {provider} API. Check your connection") from None
    if last is not None and "CERTIFICATE_VERIFY_FAILED" in str(last):
        raise ProviderError(f"Couldn't reach the {provider} API: the secure connection was rejected (a certificate check failed). "
                            "Antivirus HTTPS scanning or a proxy on this computer or network is the usual cause. Try again, or turn that scanning off for this app") from None
    raise ProviderError(f"Couldn't reach the {provider} API. Check your connection") from None
