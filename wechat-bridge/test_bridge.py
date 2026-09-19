"""Regression tests for the local WeChat bridge.

These tests use only the Python standard library.  The Worker request test
talks to an in-process HTTP server, so it never uses the deployed service or
any real access code.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("bridge.py")
SPEC = importlib.util.spec_from_file_location("airicheng_wechat_bridge", MODULE_PATH)
assert SPEC and SPEC.loader
bridge = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bridge
SPEC.loader.exec_module(bridge)


class FakeChat:
    who = bridge.DEFAULT_CHAT

    def ChatInfo(self):
        return {"nickname": bridge.DEFAULT_CHAT}


def task_message(**changes):
    value = {
        "type": "Text",
        "content": "请于明天18:00前提交实验报告",
        "sender": "老师",
        "time": "2026-09-18T15:00:00+08:00",
        "hash": "stable-message-1",
    }
    value.update(changes)
    return value


class MessageTests(unittest.TestCase):
    def test_exact_chat_and_text_only(self):
        self.assertIsNotNone(
            bridge.normalize_message(task_message(), FakeChat(), bridge.DEFAULT_CHAT)
        )
        self.assertIsNone(
            bridge.normalize_message(task_message(), FakeChat(), "另一个群")
        )
        self.assertIsNone(
            bridge.normalize_message(task_message(type="Image"), FakeChat(), bridge.DEFAULT_CHAT)
        )

    def test_stable_id_ignores_refreshed_display_time(self):
        first = bridge.normalize_message(task_message(), FakeChat(), bridge.DEFAULT_CHAT)
        second = bridge.normalize_message(
            task_message(time="2026-09-18T15:05:00+08:00"),
            FakeChat(),
            bridge.DEFAULT_CHAT,
        )
        self.assertEqual(first["fingerprint"], second["fingerprint"])

    def test_task_filter_is_conservative(self):
        self.assertTrue(bridge.looks_like_task("请于明天18:00前提交实验报告"))
        self.assertFalse(bridge.looks_like_task("今晚一起吃饭吗"))


class EventStoreTests(unittest.TestCase):
    def test_baseline_is_persisted_without_marking_messages_done(self):
        with tempfile.TemporaryDirectory() as directory:
            store = bridge.EventStore(Path(directory))
            store.mark_baseline({"old-message"})
            self.assertTrue(store.baseline_ready)
            self.assertTrue(store.is_known("old-message"))
            self.assertFalse(store.is_done("old-message"))
            restarted = bridge.EventStore(Path(directory))
            self.assertTrue(restarted.baseline_ready)
            self.assertTrue(restarted.is_known("old-message"))

    def test_success_is_idempotent_across_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = bridge.EventStore(root)
            event = bridge.normalize_message(task_message(), FakeChat(), bridge.DEFAULT_CHAT)
            self.assertTrue(store.save_pending(event))
            store.mark_done(event, {"candidates": []})
            self.assertTrue(store.is_done(event["fingerprint"]))
            self.assertFalse(store.save_pending(event))

            restarted = bridge.EventStore(root)
            self.assertTrue(restarted.is_done(event["fingerprint"]))
            self.assertFalse(restarted.save_pending(event))


class SingleScanTests(unittest.TestCase):
    def main_window(self, name=bridge.DEFAULT_CHAT):
        # No detached window or listener API: this reproduces the real failure.
        wx = Mock(spec=["ChatInfo", "ChatWith", "GetAllMessage"])
        wx.ChatInfo.return_value = {"chat_name": name, "chat_type": "group"}
        wx.GetAllMessage.return_value = [task_message()]
        return wx

    def test_open_target_needs_no_subwindow_or_switch(self):
        wx = self.main_window()
        chat = bridge.single_scan_chat(wx, bridge.DEFAULT_CHAT)
        self.assertEqual(chat.GetAllMessage(), [task_message()])
        wx.ChatWith.assert_not_called()

    def test_switch_is_exact_and_verified(self):
        wx = self.main_window("另一个群")
        def switch(name, exact):
            wx.ChatInfo.return_value = {"chat_name": name}
        wx.ChatWith.side_effect = switch
        chat = bridge.single_scan_chat(wx, bridge.DEFAULT_CHAT)
        self.assertEqual(chat.GetAllMessage(), [task_message()])
        wx.ChatWith.assert_called_once_with(bridge.DEFAULT_CHAT, exact=True)

    def test_failed_switch_reads_no_messages(self):
        wx = self.main_window("相似群名")
        with self.assertRaises(RuntimeError):
            bridge.single_scan_chat(wx, bridge.DEFAULT_CHAT)
        wx.GetAllMessage.assert_not_called()

    def test_switch_during_read_discards_snapshot(self):
        wx = self.main_window()
        chat = bridge.single_scan_chat(wx, bridge.DEFAULT_CHAT)
        def read():
            wx.ChatInfo.return_value = {"chat_name": "另一个群"}
            return [task_message()]
        wx.GetAllMessage.side_effect = read
        with self.assertRaises(RuntimeError):
            chat.GetAllMessage()

    def test_once_processes_new_message_and_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = bridge.BridgeRunner(bridge.BridgeConfig(
                bridge.DEFAULT_CHAT, "http://unused.invalid", "", Path(directory),
                dry_run=True, poll=True, poll_once=True,
            ))
            runner.store.mark_baseline({"previous-message"})
            runner.wx = self.main_window()
            runner._scan_once()
            self.assertEqual(len(list((Path(directory) / "done").glob("*.json"))), 1)
            self.assertFalse(runner.worker.is_alive())
            runner.wx.ChatWith.assert_not_called()

    def test_read_failure_is_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = bridge.BridgeRunner(bridge.BridgeConfig(
                bridge.DEFAULT_CHAT, "http://unused.invalid", "", Path(directory),
                dry_run=True, poll=True, poll_once=True,
            ))
            runner.wx = self.main_window()
            runner.wx.GetAllMessage.side_effect = RuntimeError("window closed")
            with self.assertRaises(RuntimeError):
                runner._scan_once()
            self.assertFalse(runner.store.baseline_ready)
            self.assertFalse(runner.worker.is_alive())


class WorkerClientTests(unittest.TestCase):
    def test_request_shape_and_bearer_header(self):
        received = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("content-length", "0"))
                received["path"] = self.path
                received["authorization"] = self.headers.get("authorization")
                received["user_agent"] = self.headers.get("user-agent")
                received["body"] = json.loads(self.rfile.read(length).decode("utf-8"))
                if received["body"] == {}:
                    response = json.dumps({"error": "empty"}).encode("utf-8")
                    self.send_response(400)
                else:
                    response = json.dumps({"candidates": []}).encode("utf-8")
                    self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

            def log_message(self, _format, *_args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            event = bridge.normalize_message(task_message(), FakeChat(), bridge.DEFAULT_CHAT)
            client = bridge.WorkerClient(
                f"http://127.0.0.1:{server.server_port}", "local-test-code"
            )
            self.assertEqual(client.check_access(), 400)
            status, result = client.extract(event)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(status, 200)
        self.assertEqual(result, {"candidates": []})
        self.assertEqual(received["path"], "/api/extract")
        self.assertEqual(received["authorization"], "Bearer local-test-code")
        self.assertEqual(received["user_agent"], "kexu-campus-wechat-bridge/0.1")
        self.assertEqual(
            received["body"],
            {
                "text": event["text"],
                "source": bridge.DEFAULT_CHAT,
                "reference": "2026-09-18",
                "tasks": [],
            },
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
