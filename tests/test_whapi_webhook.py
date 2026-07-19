import http.client
import json
import queue
import sys
import threading
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "linux"))
import server  # noqa: E402


class WhapiWebhookTests(unittest.TestCase):
    def setUp(self):
        self.events = queue.Queue()
        self.httpd = server.create_server(self.events, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.httpd.server_address[1]

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)

    def request(self, method, path, payload=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"} if body else {}
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        data = json.loads(response.read())
        conn.close()
        return response.status, data

    def test_incoming_text_is_normalized_and_queued(self):
        payload = {
            "messages": [{
                "id": "message-1",
                "from_me": False,
                "type": "text",
                "from": "919999999999",
                "from_name": "Gerald",
                "text": {"body": "Hello   from WhatsApp\n"},
            }],
            "event": {"type": "messages", "event": "post"},
            "channel_id": "test-channel",
        }
        status, result = self.request("POST", "/whatsapp-webhook", payload)
        self.assertEqual(status, 200)
        self.assertEqual(result["processed"], 1)
        self.assertEqual(
            self.events.get_nowait(),
            ("whatsapp", "whatsapp_message", "Gerald: Hello from WhatsApp"),
        )

    def test_outgoing_messages_and_statuses_do_not_notify_robot(self):
        outgoing = {
            "messages": [{"from_me": True, "type": "text", "text": {"body": "sent"}}],
            "event": {"type": "messages", "event": "post"},
        }
        status_event = {
            "statuses": [{"id": "message-1", "status": "read"}],
            "event": {"type": "statuses", "event": "post"},
        }
        self.assertEqual(self.request("POST", "/whatsapp-webhook", outgoing)[0], 200)
        self.assertEqual(self.request("POST", "/whatsapp-webhook", status_event)[0], 200)
        self.assertTrue(self.events.empty())

    def test_health_and_invalid_json(self):
        status, result = self.request("GET", "/whatsapp-webhook")
        self.assertEqual(status, 200)
        self.assertEqual(result["service"], "whapi-webhook")

        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        conn.request("POST", "/whatsapp-webhook", body=b"not-json")
        response = conn.getresponse()
        self.assertEqual(response.status, 400)
        response.read()
        conn.close()


if __name__ == "__main__":
    unittest.main()
