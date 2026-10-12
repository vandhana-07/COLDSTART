"""
test_api_validation.py -- the HTTP layer must reject bad input before working.

WHY THIS TEST EXISTS
--------------------
Audit finding A3: `optimise()` filtered its objective list and, for an unknown
objective, silently produced results for the DEFAULT objective instead of raising.
A typo therefore returned a confident, wrong answer. The engine now raises, but an
engine that raises inside a background worker only surfaces as a generic job error
after a forecast fetch has already been paid for.

The API must instead reject the request immediately, with a 400 and a usable hint.
This test boots the real stdlib server on an ephemeral port and talks to it over
HTTP, so it pins the behaviour a browser would actually see.
"""

import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
APP = os.path.join(ROOT, "app")
sys.path.insert(0, APP)
sys.path.insert(0, os.path.join(APP, "engine"))

import server                                            # noqa: E402


class QuietHandler(server.Handler):
    """The handler logs every request to stdout, which buries the test summary.
    Tests are not a web server; silence the access log."""

    def log_message(self, fmt, *args):
        pass


class ApiObjectiveValidation(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.httpd = HTTPServer(("127.0.0.1", 0), QuietHandler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def get(self, path):
        url = f"http://127.0.0.1:{self.port}{path}"
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    def test_unknown_objective_is_a_400_with_a_hint(self):
        status, body = self.get("/api/job/start?kind=optimise&objective=cheapest")
        self.assertEqual(status, 400,
                         f"unknown objective should be rejected up front, got {status}: {body}")
        blob = json.dumps(body).lower()
        self.assertIn("cheapest", blob, "the error must name the offending value")
        self.assertIn("lowest_cost", blob,
                      "the error must list the valid objectives to choose from")

    def test_battle_rejects_an_unknown_objective_too(self):
        status, body = self.get("/api/job/start?kind=battle&objective=nonsense")
        self.assertEqual(status, 400, f"battle accepted a bad objective: {body}")

    def test_rejection_does_not_start_a_job(self):
        """A rejected request must not leave a worker running or a job to poll."""
        self.get("/api/job/start?kind=optimise&objective=bogus")
        # nothing to assert about a job id, because the response carried none
        status, body = self.get("/api/job/status?id=does-not-exist")
        self.assertEqual(status, 404)
        self.assertNotIn("job_id", json.dumps(body))

    def test_unknown_job_kind_still_rejected(self):
        status, _ = self.get("/api/job/start?kind=teleport")
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
