"""Browser-presence watchdog: unit tests (fake clock) and real `qbible serve` processes."""

import http.client
import json
import os
import re
import subprocess
import sys
import time
import unittest

from qbible.watchdog import Watchdog

from .helpers import ROOT, IsolatedEnv, require_kjv


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class WatchdogUnitTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.fired = 0
        self.wd = Watchdog(self.on_idle, visible_timeout=15, hidden_timeout=150, close_grace=5, clock=self.clock)

    def on_idle(self):
        self.fired += 1

    def advance(self, seconds):
        self.clock.now += seconds
        return self.wd.check()

    def test_not_armed_until_first_heartbeat(self):
        self.assertFalse(self.advance(10_000))
        self.assertEqual(self.fired, 0)

    def test_visible_page_keeps_alive_then_expires(self):
        self.wd.heartbeat("a")
        self.assertFalse(self.advance(10))
        self.wd.heartbeat("a")
        self.assertFalse(self.advance(14))
        self.assertTrue(self.advance(2))
        self.assertEqual(self.fired, 1)
        self.assertFalse(self.advance(100))  # fires only once
        self.assertEqual(self.fired, 1)

    def test_hidden_page_gets_a_longer_lease(self):
        self.wd.heartbeat("a", visible=False)
        self.assertFalse(self.advance(100))  # throttled background tab: still alive
        self.assertTrue(self.advance(60))

    def test_becoming_visible_shortens_the_lease(self):
        self.wd.heartbeat("a", visible=False)
        self.wd.heartbeat("a", visible=True)
        self.assertTrue(self.advance(16))

    def test_closing_page_stops_quickly(self):
        self.wd.heartbeat("a")
        self.wd.heartbeat("a", closing=True)
        self.assertFalse(self.advance(4))
        self.assertTrue(self.advance(2))

    def test_reload_keeps_server_alive(self):
        self.wd.heartbeat("old")
        self.wd.heartbeat("old", closing=True)
        self.advance(1)
        self.wd.heartbeat("new")  # the reloaded page
        self.assertFalse(self.advance(10))

    def test_any_open_page_keeps_server_alive(self):
        self.wd.heartbeat("a")
        self.wd.heartbeat("b", visible=False)
        self.wd.heartbeat("a", closing=True)
        self.assertFalse(self.advance(100))
        self.assertTrue(self.advance(60))

    def test_startup_allowance_when_qbible_opens_the_browser(self):
        self.wd.expect_connection(60)
        self.assertFalse(self.advance(59))
        self.assertTrue(self.advance(2))  # no page ever connected
        self.assertFalse(self.wd.page_connected)

    def test_startup_allowance_is_replaced_by_the_first_page(self):
        self.wd.expect_connection(60)
        self.advance(5)
        self.wd.heartbeat("a")
        self.wd.heartbeat("a", closing=True)  # closed quickly: no need to wait out the allowance
        self.assertTrue(self.advance(6))
        self.assertTrue(self.wd.page_connected)

    def test_client_ids_are_validated_and_bounded(self):
        for bad in ["", "x" * 65, "a b", "../", None, 5]:
            with self.assertRaises(ValueError):
                self.wd.heartbeat(bad)
        for i in range(400):
            self.wd.heartbeat(f"c{i}")
        self.assertLessEqual(len(self.wd._leases), 256)

    def test_invalid_timeouts_rejected(self):
        with self.assertRaises(ValueError):
            Watchdog(lambda: None, visible_timeout=10, hidden_timeout=5)

    def test_interval_is_a_third_of_the_visible_timeout(self):
        self.assertEqual(self.wd.interval_ms, 5000)


class ServeProcessTests(unittest.TestCase):
    """Run the real `qbible serve` command and drive it with heartbeats."""

    def setUp(self):
        require_kjv()
        self.env_ctx = IsolatedEnv().__enter__()
        self.procs = []

    def tearDown(self):
        for p in self.procs:
            if p.poll() is None:
                p.kill()
            p.wait()
            p.stderr.close()
        self.env_ctx.__exit__(None, None, None)

    def start(self, *args, timeouts="1.5,3,0.5"):
        env = os.environ.copy()
        env["QBIBLE_WATCHDOG_TIMEOUTS"] = timeouts
        p = subprocess.Popen([sys.executable, "-m", "qbible", "serve", "--port", "0", *args], cwd=ROOT,
                             env=env, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
        self.procs.append(p)
        line = p.stderr.readline()
        m = re.search(r"http://127\.0\.0\.1:(\d+)/", line)
        self.assertIsNotNone(m, line)
        return p, int(m.group(1))

    def call(self, port, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        headers = {"Host": f"127.0.0.1:{port}"}
        if body is not None:
            headers.update({"Content-Type": "application/json", "X-QBible-Request": "1"})
        conn.request(method, path, json.dumps(body) if body is not None else None, headers)
        r = conn.getresponse()
        data = json.loads(r.read() or b"null")
        conn.close()
        return r.status, data

    def wait_exit(self, p, timeout):
        try:
            return p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None

    def test_stops_after_pages_close_but_not_before(self):
        p, port = self.start()
        status, info = self.call(port, "GET", "/api/v1/info")
        self.assertEqual(info["watchdog"], {"interval_ms": 500})
        # Not armed until a page connects: survives well beyond the timeout.
        self.assertIsNone(self.wait_exit(p, 2.5))
        for _ in range(6):  # an open page pinging keeps it alive
            self.assertEqual(self.call(port, "POST", "/api/v1/heartbeat", {"client": "page1", "visible": True})[0], 200)
            time.sleep(0.5)
        self.assertIsNone(p.poll())
        self.call(port, "POST", "/api/v1/heartbeat", {"client": "page1", "closing": True})
        self.assertEqual(self.wait_exit(p, 5), 0)
        self.assertIn("All qbible browser pages were closed", p.stderr.read())

    def test_keep_running_disables_the_watchdog(self):
        p, port = self.start("--keep-running")
        status, info = self.call(port, "GET", "/api/v1/info")
        self.assertIsNone(info["watchdog"])
        self.assertEqual(self.call(port, "POST", "/api/v1/heartbeat", {"client": "page1"})[1], {"watchdog": False})
        self.call(port, "POST", "/api/v1/heartbeat", {"client": "page1", "closing": True})
        self.assertIsNone(self.wait_exit(p, 3))

    def test_config_setting_disables_the_watchdog(self):
        from .helpers import run_cli
        self.assertEqual(run_cli("config", "set", "server.exit_when_closed", "false")[0], 0)
        p, port = self.start()
        self.assertIsNone(self.call(port, "GET", "/api/v1/info")[1]["watchdog"])
        p2, port2 = self.start("--exit-when-closed")  # flag overrides config
        self.assertIsNotNone(self.call(port2, "GET", "/api/v1/info")[1]["watchdog"])

    def test_heartbeat_requires_same_origin_json(self):
        p, port = self.start()
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("POST", "/api/v1/heartbeat", json.dumps({"client": "x", "closing": True}),
                     {"Host": f"127.0.0.1:{port}", "Content-Type": "application/json"})
        self.assertEqual(conn.getresponse().status, 403)  # no X-QBible-Request header
        conn.close()
        self.assertEqual(self.call(port, "POST", "/api/v1/heartbeat", {"client": "bad id!"})[0], 400)
        self.assertEqual(self.call(port, "POST", "/api/v1/heartbeat", {"client": "x", "visible": "yes"})[0], 400)

    def test_open_stops_if_no_page_ever_connects(self):
        # BROWSER=true makes Python's webbrowser module run `true URL` instead of a browser.
        os.environ["BROWSER"] = "true"
        p, port = self.start("--open", timeouts="1,2,0.5,2")
        self.assertEqual(self.wait_exit(p, 8), 0)
        self.assertIn("No browser page connected", p.stderr.read())

    def test_second_launch_with_open_reuses_the_running_server(self):
        os.environ["BROWSER"] = "true"
        p, port = self.start()
        env = os.environ.copy()
        r = subprocess.run([sys.executable, "-m", "qbible", "serve", "--open", "--port", str(port)], cwd=ROOT,
                           env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"qbible is already running at http://127.0.0.1:{port}/", r.stderr)
        self.assertIsNone(p.poll(), "the first server keeps running")
        # Without --open a busy port is still an error.
        r = subprocess.run([sys.executable, "-m", "qbible", "serve", "--port", str(port)], cwd=ROOT,
                           env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 4)
        self.assertIn("Cannot listen", r.stderr)

    def test_refused_on_non_loopback_addresses(self):
        # Checked before binding, so nothing is ever exposed on the network.
        r = subprocess.run([sys.executable, "-m", "qbible", "serve", "--host", "0.0.0.0", "--allow-remote",
                            "--exit-when-closed", "--port", "0"], cwd=ROOT, env=os.environ.copy(),
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 2)
        self.assertIn("only available on a loopback address", r.stderr)

    def test_bad_timeout_environment_is_a_usage_error(self):
        env = os.environ.copy()
        env["QBIBLE_WATCHDOG_TIMEOUTS"] = "5,1,1"
        r = subprocess.run([sys.executable, "-m", "qbible", "serve", "--port", "0"], cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 2)
        self.assertIn("QBIBLE_WATCHDOG_TIMEOUTS", r.stderr)


if __name__ == "__main__":
    unittest.main()
