import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).parents[1] / "linux"))

import swiggy_tool


class SwiggyAuthTests(unittest.TestCase):
    def setUp(self):
        swiggy_tool._auth.update(access_token="", expires_at=None, client_id=None,
                                 state=None, verifier=None)
        swiggy_tool.reset_session()

    @patch("swiggy_tool.requests.post")
    def test_local_pkce_flow(self, post):
        registration = Mock()
        registration.json.return_value = {"client_id": "local-client"}
        registration.raise_for_status.return_value = None
        exchange = Mock()
        exchange.json.return_value = {"access_token": "secret", "expires_in": 3600}
        exchange.raise_for_status.return_value = None
        post.side_effect = [registration, exchange]

        auth_url = swiggy_tool.begin_auth()
        query = parse_qs(urlsplit(auth_url).query)
        self.assertEqual(query["redirect_uri"], [swiggy_tool.CALLBACK])
        self.assertEqual(query["code_challenge_method"], ["S256"])

        swiggy_tool.finish_auth("authorization-code", query["state"][0])
        self.assertTrue(swiggy_tool.auth_status()["authenticated"])
        token_request = post.call_args_list[1].kwargs["json"]
        self.assertEqual(token_request["redirect_uri"], swiggy_tool.CALLBACK)
        self.assertTrue(token_request["code_verifier"])

    def test_callback_rejects_bad_state(self):
        swiggy_tool._auth["state"] = "expected"
        with self.assertRaisesRegex(ValueError, "invalid OAuth state"):
            swiggy_tool.finish_auth("code", "wrong")


if __name__ == "__main__":
    unittest.main()
