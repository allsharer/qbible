"""Browser-presence watchdog: stop the local server when its pages are closed.

Every open qbible page sends a heartbeat (``POST /api/v1/heartbeat``) with a
random per-page id and whether it is visible. Each page holds a *lease*:

* visible page — ``visible_timeout`` seconds (pings arrive every
  ``visible_timeout / 3`` seconds, so about three may be missed);
* hidden page — ``hidden_timeout`` seconds, because browsers throttle timers
  in background tabs (Chrome: about once a minute);
* page being closed or reloaded — ``close_grace`` seconds, long enough for a
  reloaded page to send its first ping.

The watchdog is armed by the first heartbeat, so the server never stops
before a browser has connected, unless qbible opened the browser itself
(:meth:`Watchdog.expect_connection`), in which case the first page has a
startup allowance. Once armed, when no page holds a lease the ``on_idle``
callback runs once (normally ``httpd.shutdown``).

``time.monotonic`` is used, which on Linux does not advance during system
suspend, so a sleeping laptop does not count as "all pages closed".
"""

from __future__ import annotations

import re
import threading
import time
from typing import Callable

_CLIENT_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_CLIENTS = 256
_STARTUP = " startup"  # not a valid client id, so pages cannot collide with it


class Watchdog:
    def __init__(self, on_idle: Callable[[], None], *, visible_timeout: float = 15.0,
                 hidden_timeout: float = 150.0, close_grace: float = 5.0,
                 clock: Callable[[], float] = time.monotonic):
        if not (0 < close_grace <= visible_timeout <= hidden_timeout):
            raise ValueError("timeouts must satisfy 0 < close_grace <= visible <= hidden")
        self.on_idle = on_idle
        self.visible_timeout = visible_timeout
        self.hidden_timeout = hidden_timeout
        self.close_grace = close_grace
        self.clock = clock
        self._leases: dict[str, float] = {}
        self._armed = False
        self._fired = False
        self.page_connected = False
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def interval_ms(self) -> int:
        """How often visible pages should ping."""
        return max(250, int(self.visible_timeout * 1000 / 3))

    @staticmethod
    def valid_client(client: object) -> bool:
        return isinstance(client, str) and bool(_CLIENT_RE.match(client))

    def expect_connection(self, within: float) -> None:
        """Arm now, allowing ``within`` seconds for the first page to connect.

        Used when qbible opens the browser itself (e.g. from the app launcher), so
        a background server does not run forever if no page ever arrives.
        """
        with self._lock:
            self._armed = True
            self._leases[_STARTUP] = self.clock() + within

    def heartbeat(self, client: str, *, visible: bool = True, closing: bool = False) -> None:
        if not self.valid_client(client):
            raise ValueError("invalid client id")
        now = self.clock()
        lease = self.close_grace if closing else (self.visible_timeout if visible else self.hidden_timeout)
        with self._lock:
            self._armed = True
            self.page_connected = True
            self._leases.pop(_STARTUP, None)  # a real page has connected
            self._leases[client] = now + lease
            if len(self._leases) > MAX_CLIENTS:  # drop the soonest-expiring leases
                for k in sorted(self._leases, key=self._leases.get)[: len(self._leases) - MAX_CLIENTS]:
                    del self._leases[k]

    def active_clients(self) -> int:
        now = self.clock()
        with self._lock:
            return sum(1 for d in self._leases.values() if d > now)

    def check(self) -> bool:
        """Run one check; returns True if the idle callback fired."""
        now = self.clock()
        with self._lock:
            if not self._armed or self._fired:
                return False
            self._leases = {k: d for k, d in self._leases.items() if d > now}
            if self._leases:
                return False
            self._fired = True
        self.on_idle()
        return True

    # -- background thread -------------------------------------------------------
    def start(self, poll: float = 1.0) -> None:
        def run():
            while not self._stop.wait(poll):
                if self.check():
                    break

        self._thread = threading.Thread(target=run, name="qbible-watchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
