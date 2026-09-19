"""Local personal-WeChat -> AIricheng bridge.

This process is deliberately local. It uses wxauto4's UI listener, watches one
explicit chat, keeps a small local outbox for retry/idempotency, and calls the
already deployed Worker /api/extract endpoint. It never sends a WeChat message
and never prints a secret.

The default runtime data directory is outside the repository:
%LOCALAPPDATA%\\AIricheng\\wechat-bridge
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import queue
import re
import signal
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BEIJING = timezone(timedelta(hours=8))
DEFAULT_WORKER = "https://kexu-campus-mvp.richeng.workers.dev"
DEFAULT_CHAT = "微信接入测试"
MAX_TEXT = 12000


# A message is forwarded only when it looks like an instruction and either
# names a task-like object or contains a deadline/time. This intentionally
# favours a false negative over uploading ordinary conversation.
ACTION_RE = re.compile(
    r"请|需要|务必|记得|完成|提交|上交|交作业|报名|签到|参加|参会|开会|填写|填报|准备|缴费|截止|延期|改到|改为|取消|不必交|不用交|已提交|已完成"
)
OBJECT_RE = re.compile(
    r"作业|任务|报告|论文|实验|考试|测验|材料|申请|表格|项目|竞赛|比赛|会议|开会|活动|讲座|课程|答辩|文件|名单|信息|报名|签到|缴费|通知"
)
DEADLINE_RE = re.compile(
    r"截止|之前|前提交|前完成|今天|今晚|明天|后天|上午|下午|晚上|本周|下周|星期|周[一二三四五六日天]|\d{1,4}\s*[月日号]|\d{1,2}[:：]\d{2}"
)


def _value(obj: Any, *names: str, default: Any = None) -> Any:
    """Read a mapping key or an attribute without assuming wxauto4 fields."""

    if obj is None:
        return default
    if isinstance(obj, Mapping):
        for name in names:
            if name in obj and obj[name] not in (None, ""):
                return obj[name]
    for name in names:
        try:
            result = getattr(obj, name)
        except Exception:
            continue
        try:
            result = result() if callable(result) else result
        except Exception:
            continue
        if result not in (None, ""):
            return result
    return default


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Mapping):
        return str(_value(value, "name", "nickname", "display_name", "id", default=""))
    return str(value)


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=BEIJING)
        return value.astimezone(BEIJING).isoformat(timespec="seconds")
    raw = _as_text(value).strip()
    return raw or datetime.now(BEIJING).isoformat(timespec="seconds")


def _chat_name(chat: Any, fallback: str = "") -> str:
    info = _value(chat, "ChatInfo", "chat_info", default={})
    if not isinstance(info, Mapping):
        info = {}
    return _as_text(
        _value(
            info,
            "nickname",
            "chat_name",
            "name",
            "display_name",
            default=_value(chat, "who", "nickname", "name", default=fallback),
        )
    ).strip()


class ExactChatReader:
    """Read the main chat only while its live title matches the allowlist."""

    def __init__(self, chat: Any, target: str):
        self.chat = chat
        self.target = target

    def ChatInfo(self) -> dict[str, str]:
        # Message normalization uses the identity of the verified snapshot.
        return {"chat_name": self.target}

    def _check_target(self) -> None:
        if _chat_name(self.chat) != self.target:
            raise RuntimeError("聊天窗口已切换或无法确认群名，本次扫描已停止；请保持目标群打开。")

    def GetAllMessage(self) -> list[Any]:
        self._check_target()
        messages = list(self.chat.GetAllMessage() or [])
        self._check_target()
        return messages


def single_scan_chat(wx: Any, target: str) -> ExactChatReader:
    # GetSubWindow only finds a detached chat window. A single scan does not
    # register a listener (which used to open that window), so use the main UI.
    if _chat_name(wx) != target:
        wx.ChatWith(target, exact=True)
    reader = ExactChatReader(wx, target)
    reader._check_target()
    return reader


def _is_text_message(message: Any) -> bool:
    kind = _as_text(_value(message, "type", "msg_type", "message_type", default="")).lower()
    if not kind:
        # Some wxauto4 releases expose content but omit type on lightweight
        # message objects. The content check still keeps this text-only.
        return bool(_value(message, "content", "text", "message", default=""))
    return "text" in kind or kind in {"txt", "plain", "1"}


def normalize_message(message: Any, chat: Any, target_chat: str) -> dict[str, Any] | None:
    """Convert a wxauto4 callback object into the stable UnifiedMessage shape."""

    if not _is_text_message(message):
        return None
    # wxauto4 exposes these as properties in some versions and methods in
    # others. System notifications are never forwarded.
    if bool(_value(message, "is_system", "system", default=False)):
        return None
    text = _as_text(_value(message, "content", "text", "message", default="")).strip()
    if not text or len(text) > MAX_TEXT:
        return None

    chat_name = _chat_name(chat, target_chat) or target_chat
    # AddListenChat is registered with the exact display name. Keep a second
    # check here so a fuzzy match or a changed window cannot leak another chat.
    if chat_name.strip() != target_chat.strip():
        return None

    sender = _value(message, "sender", "sender_name", "from_user", "author", default="")
    sender_name = _as_text(sender).strip()
    sender_id = _as_text(_value(message, "sender_id", "from_id", default="")).strip()
    if isinstance(sender, Mapping):
        sender_id = sender_id or _as_text(_value(sender, "id", "wxid", "username", default=""))
        sender_name = sender_name or _as_text(_value(sender, "name", "nickname", default=""))

    sent_at = _iso(
        _value(message, "sent_at", "create_time", "time", "timestamp", "date", default=None)
    )
    stable_id = _as_text(_value(message, "message_id", "id", "msg_id", "hash", "hash_text", default="")).strip()
    # wxauto4 can expose a stable hash/id. Prefer it because some UI builds
    # refresh the displayed timestamp while the same row is re-read. Fall
    # back to the documented chat + sender + time + text fingerprint.
    fingerprint_source = (
        "|".join((chat_name, "message-id", stable_id))
        if stable_id
        else "|".join((chat_name, sender_name, sent_at, text))
    )
    fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()
    return {
        "platform": "personal_wechat",
        "chat_id": _as_text(_value(chat, "chat_id", "id", "who", default=chat_name)),
        "chat_name": chat_name,
        "message_id": stable_id or fingerprint,
        "sender_id": sender_id,
        "sender_name": sender_name or "未知发送者",
        "sent_at": sent_at,
        "text": text,
        "attachments": [],
        "fingerprint": fingerprint,
    }


def looks_like_task(text: str) -> bool:
    text = text.strip()
    if not text:
        return False
    has_action = bool(ACTION_RE.search(text))
    has_object = bool(OBJECT_RE.search(text))
    has_deadline = bool(DEADLINE_RE.search(text))
    return (has_action and has_object) or (has_object and has_deadline) or (has_action and has_deadline)


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


class EventStore:
    """Outbox and idempotency state, kept outside the Git workspace."""

    def __init__(self, root: Path):
        self.root = root
        self.pending = root / "pending"
        self.done = root / "done"
        self.failed = root / "failed"
        self.state_file = root / "state.json"
        for directory in (self.pending, self.done, self.failed):
            directory.mkdir(parents=True, exist_ok=True)
        try:
            state = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        self.seen = set(str(item) for item in state.get("seen", []))
        self.ignored = set(str(item) for item in state.get("ignored", []))
        self.baseline_ready = bool(state.get("baseline_ready", False))
        self.lock = threading.Lock()

    def _save_state(self) -> None:
        _atomic_json(
            self.state_file,
            {
                "version": 2,
                "baseline_ready": self.baseline_ready,
                "seen": sorted(self.seen)[-5000:],
                "ignored": sorted(self.ignored)[-5000:],
            },
        )

    def is_done(self, fingerprint: str) -> bool:
        with self.lock:
            return fingerprint in self.seen

    def save_pending(self, event: dict[str, Any]) -> bool:
        fingerprint = event["fingerprint"]
        with self.lock:
            if fingerprint in self.seen:
                return False
            path = self.pending / f"{fingerprint}.json"
            if not path.exists():
                _atomic_json(path, event)
            return True

    def pending_events(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for path in sorted(self.pending.glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(value, dict) and value.get("fingerprint"):
                    result.append(value)
            except (OSError, ValueError):
                continue
        return result

    def mark_done(self, event: dict[str, Any], result: dict[str, Any]) -> None:
        fingerprint = event["fingerprint"]
        with self.lock:
            _atomic_json(self.done / f"{fingerprint}.json", {"event": event, "result": result})
            self.seen.add(fingerprint)
            self.ignored.discard(fingerprint)
            self._save_state()
            try:
                (self.pending / f"{fingerprint}.json").unlink()
            except FileNotFoundError:
                pass

    def mark_baseline(self, fingerprints: set[str]) -> None:
        """Persist visible messages as ignored before one-shot scanning."""

        with self.lock:
            for fingerprint in fingerprints:
                if fingerprint in self.seen:
                    continue
                if (self.pending / f"{fingerprint}.json").exists():
                    continue
                if (self.failed / f"{fingerprint}.json").exists():
                    continue
                self.ignored.add(fingerprint)
            self.baseline_ready = True
            self._save_state()

    def is_known(self, fingerprint: str) -> bool:
        with self.lock:
            return fingerprint in self.seen or fingerprint in self.ignored

    def mark_failed(self, event: dict[str, Any], error: str) -> None:
        # Keep the original event for a later explicit retry, but record the
        # safe status separately. No upstream response body is stored.
        _atomic_json(self.failed / f"{event['fingerprint']}.json", {"event": event, "error": error})
        try:
            (self.pending / f"{event['fingerprint']}.json").unlink()
        except FileNotFoundError:
            pass

    def failed_events(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for path in sorted(self.failed.glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                event = value.get("event") if isinstance(value, dict) else None
                if isinstance(event, dict) and event.get("fingerprint"):
                    result.append(event)
            except (OSError, ValueError):
                continue
        return result


class WorkerClient:
    def __init__(self, base_url: str, access_token: str = "", timeout: int = 40):
        base_url = base_url.rstrip("/")
        self.url = base_url if base_url.endswith("/api/extract") else f"{base_url}/api/extract"
        self.access_token = access_token.strip()
        self.timeout = timeout

    def check_access(self) -> int:
        """Validate endpoint access without sending message text or calling AI.

        The deployed Worker authenticates before validating the request body.
        An authorized empty JSON request therefore returns 400, while a bad
        access code returns 401.  No model request is made for either result.
        """

        headers = {
            "content-type": "application/json",
            "accept": "application/json",
            "user-agent": "kexu-campus-wechat-bridge/0.1",
        }
        if self.access_token:
            headers["authorization"] = f"Bearer {self.access_token}"
        request = Request(
            self.url,
            data=b"{}",
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return int(response.status)
        except HTTPError as error:
            return int(error.code)
        except (URLError, TimeoutError, OSError):
            return 0

    def extract(self, event: dict[str, Any]) -> tuple[int, dict[str, Any] | None]:
        payload = {
            "text": event["text"],
            "source": event["chat_name"],
            "reference": event["sent_at"][:10],
            # The browser's task list is local to that browser. The bridge
            # therefore sends no guessed task IDs; the web inbox remains the
            # place for a human to associate updates.
            "tasks": [],
        }
        headers = {
            "content-type": "application/json",
            "accept": "application/json",
            "user-agent": "kexu-campus-wechat-bridge/0.1",
        }
        if self.access_token:
            headers["authorization"] = f"Bearer {self.access_token}"
        request = Request(self.url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                status = int(response.status)
                body = response.read()
        except HTTPError as error:
            # Never print or persist upstream body text: an intermediary must
            # not accidentally echo credentials or private provider details.
            return int(error.code), None
        except (URLError, TimeoutError, OSError):
            return 0, None
        try:
            value = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            value = None
        return status, value if isinstance(value, dict) else None


@dataclass
class BridgeConfig:
    chat_name: str
    worker_url: str
    access_token: str
    data_dir: Path
    dry_run: bool = False
    diagnostic: bool = False
    poll: bool = False
    poll_once: bool = False
    retry_failed: bool = False
    poll_retry_seconds: int = 15


class BridgeRunner:
    def __init__(self, config: BridgeConfig):
        self.config = config
        self.store = EventStore(config.data_dir)
        self.client = WorkerClient(config.worker_url, config.access_token)
        self.events: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self.stop = threading.Event()
        self.worker = threading.Thread(target=self._send_loop, name="ai-extract", daemon=True)
        self.wx: Any = None

    def _handle_message(self, message: Any, chat: Any, origin: str) -> None:
        try:
            if self.config.diagnostic:
                raw_type = _as_text(_value(message, "type", "msg_type", "message_type", default="?"))
                raw_text = _as_text(_value(message, "content", "text", "message", default=""))
                raw_chat = _chat_name(chat, self.config.chat_name) or "?"
                marker = "CALLBACK_SEEN" if origin == "callback" else "POLL_SEEN"
                print(f"[{marker}] chat={raw_chat} type={raw_type} chars={len(raw_text)}", flush=True)
            event = normalize_message(message, chat, self.config.chat_name)
            if not event or not looks_like_task(event["text"]):
                return
            if not self.store.save_pending(event):
                return
            self.events.put(event)
            print(f"[EVENT_TASK] sender={event['sender_name']} chars={len(event['text'])}", flush=True)
            print(f"[新任务消息] {event['chat_name']} / {event['sender_name']} / {event['sent_at']}: {event['text']}", flush=True)
        except Exception as exc:
            # A malformed single message must not stop the listener.
            print(f"[跳过一条消息] {type(exc).__name__}", flush=True)

    def on_message(self, message: Any, chat: Any) -> None:
        self._handle_message(message, chat, "callback")

    def _send_loop(self) -> None:
        while not self.stop.is_set():
            try:
                event = self.events.get(timeout=0.5)
            except queue.Empty:
                continue
            if event is None:
                self.events.task_done()
                return
            try:
                status, result = (200, {"dryRun": True, "candidates": []}) if self.config.dry_run else self.client.extract(event)
                if status == 200 and isinstance(result, dict) and "error" not in result:
                    self.store.mark_done(event, result)
                    count = len(result.get("candidates", [])) if isinstance(result.get("candidates"), list) else 0
                    marker = "[DRY_RUN_SAVED]" if self.config.dry_run else "[已发送到 Worker]"
                    print(f"{marker} 候选 {count} 条；结果已保存到本机", flush=True)
                    continue
                safe_status = status or "网络错误"
                # Keep the event pending, retry a small bounded number of times,
                # and write a failure record without storing the response body.
                attempts = int(event.get("attempts", 0)) + 1
                event["attempts"] = attempts
                self.store.save_pending(event)
                if attempts >= 3 or (status and 400 <= status < 500):
                    self.store.mark_failed(event, f"HTTP {status}" if status else "网络错误")
                    print(f"[发送失败] {safe_status}；消息保留在本机待重试", flush=True)
                else:
                    print(f"[发送暂时失败] {safe_status}；稍后重试", flush=True)
                    self.stop.wait(self.config.poll_retry_seconds)
                    if not self.stop.is_set():
                        self.events.put(event)
            finally:
                self.events.task_done()

    def _load_pending(self) -> None:
        for event in self.store.pending_events():
            if not self.store.is_done(event["fingerprint"]):
                self.events.put(event)
        if self.config.retry_failed:
            for event in self.store.failed_events():
                if not self.store.is_done(event["fingerprint"]):
                    self.store.save_pending(event)
                    self.events.put(event)

    def _poll_loop(self, chat: Any) -> None:
        """Targeted fallback for clients whose UI listener emits no callback."""
        baseline: set[str] = set()
        stable_rounds = 0
        previous_count = -1
        for _ in range(5):
            try:
                baseline_messages = list(chat.GetAllMessage() or [])
            except Exception as exc:
                if self.config.poll_once:
                    raise RuntimeError("读取目标群失败，本次扫描未完成。请保持目标群可见。") from exc
                print(f"[POLL_UNAVAILABLE] {type(exc).__name__}", flush=True)
                return
            for message in baseline_messages:
                event = normalize_message(message, chat, self.config.chat_name)
                if event:
                    baseline.add(event["fingerprint"])
            current_count = len(baseline)
            if current_count == previous_count:
                stable_rounds += 1
            else:
                stable_rounds = 0
            previous_count = current_count
            if stable_rounds >= 1:
                break
            if self.stop.wait(1):
                return
        if self.config.poll_once:
            if not self.store.baseline_ready:
                self.store.mark_baseline(baseline)
                print(f"[POLL_ONCE_BASELINE] recent={len(baseline)} uploaded=0", flush=True)
                return
            observed: set[str] = set()
            try:
                messages = list(chat.GetAllMessage() or [])
            except Exception as exc:
                raise RuntimeError("读取目标群失败，本次扫描未完成。请保持目标群可见。") from exc
            for message in messages:
                event = normalize_message(message, chat, self.config.chat_name)
                if not event or event["fingerprint"] in observed or self.store.is_known(event["fingerprint"]):
                    continue
                observed.add(event["fingerprint"])
                self._handle_message(message, chat, "poll")
            print(f"[POLL_ONCE_DONE] scanned={len(messages)} new={len(observed)}", flush=True)
            return
        self.store.mark_baseline(baseline)
        print(f"[POLL_BASELINE] recent={len(baseline)} uploaded=0", flush=True)
        while not self.stop.wait(2):
            try:
                messages = list(chat.GetAllMessage() or [])
            except Exception as exc:
                print(f"[POLL_RETRY] {type(exc).__name__}", flush=True)
                continue
            for message in messages:
                event = normalize_message(message, chat, self.config.chat_name)
                if not event:
                    continue
                fingerprint = event["fingerprint"]
                if fingerprint in baseline:
                    continue
                baseline.add(fingerprint)
                self._handle_message(message, chat, "poll")

    def _scan_once(self) -> None:
        chat = single_scan_chat(self.wx, self.config.chat_name)
        print(f"[SCAN_ONCE_READY] chat={self.config.chat_name} source=main-window", flush=True)
        self._load_pending()
        self.worker.start()
        try:
            # Read on the initialization thread; don't move the main UI object
            # into a polling thread or register a continuous listener.
            self._poll_loop(chat)
            deadline = time.monotonic() + 60
            while self.events.unfinished_tasks and time.monotonic() < deadline and not self.stop.is_set():
                self.stop.wait(0.2)
            if self.events.unfinished_tasks:
                raise RuntimeError("扫描已结束，但发送尚未完成；消息仍保存在本机待重试。")
        finally:
            self.stop.set()
            self.events.put(None)
            self.worker.join(timeout=3)

    def start(self) -> None:
        if not self.config.dry_run:
            access_status = self.client.check_access()
            if access_status == 401:
                raise RuntimeError("Worker 接口访问码无效，请关闭窗口后重新启动并输入正确访问码。")
            if access_status != 400:
                shown = access_status or "网络错误"
                raise RuntimeError(f"Worker 接口预检失败（{shown}），未读取或上传微信消息。")
            print("[WORKER_READY] 接口访问码验证通过（未调用模型）", flush=True)
        try:
            from wxauto4 import WeChat
        except ImportError as exc:
            raise RuntimeError("未找到 wxauto4。请在已安装 wxauto4 的 Python 环境中运行此脚本。") from exc

        try:
            self.wx = WeChat(start_listener=False, ads=False, resize=False)
        except TypeError:
            self.wx = WeChat(start_listener=False)
        if not bool(self.wx.IsOnline()):
            raise RuntimeError("微信当前不在线。请先登录个人微信并保持窗口可见。")
        if self.config.poll_once:
            self._scan_once()
            return
        self._load_pending()
        self.worker.start()
        response = self.wx.AddListenChat(self.config.chat_name, callback=self.on_message)
        if _value(response, "success", default=True) is False:
            raise RuntimeError("未能注册指定群聊监听，请检查群聊显示名称是否完全一致。")
        self.wx.StartListening()
        print(f"[BRIDGE_READY] chat={self.config.chat_name}", flush=True)
        print("[BRIDGE_WAITING] waiting for new text messages", flush=True)
        if self.config.diagnostic:
            print("[DIAGNOSTIC_ONLY] callbacks are logged locally; nothing is uploaded", flush=True)
        poll_thread = None
        if self.config.poll:
            try:
                poll_chat = self.wx.GetSubWindow(self.config.chat_name)
            except Exception:
                poll_chat = None
            if poll_chat is None:
                print("[POLL_UNAVAILABLE] target chat window not available", flush=True)
            else:
                poll_thread = threading.Thread(target=self._poll_loop, args=(poll_chat,), name="wechat-poll", daemon=True)
                poll_thread.start()
        print(f"[桥接已启动] 只监听：{self.config.chat_name}", flush=True)
        print("[安全范围] 只处理新文字消息，不读取历史、不发送微信消息；按 Ctrl+C 停止。", flush=True)
        try:
            while not self.stop.wait(1):
                pass
        finally:
            self.stop.set()
            self.events.put(None)
            if self.wx is not None:
                try:
                    self.wx.StopListening(remove=True)
                except Exception:
                    pass
            if poll_thread is not None:
                poll_thread.join(timeout=3)
            self.worker.join(timeout=3)


def default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "AIricheng" / "wechat-bridge"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="监听一个个人微信群聊，并把疑似任务交给 AIricheng Worker")
    parser.add_argument("--chat", default=os.environ.get("WECHAT_CHAT_NAME", DEFAULT_CHAT), help="完全匹配的群聊显示名称")
    parser.add_argument("--worker-url", default=os.environ.get("WECHAT_BRIDGE_WORKER_URL", DEFAULT_WORKER))
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("WECHAT_BRIDGE_DATA_DIR", default_data_dir())))
    parser.add_argument("--dry-run", action="store_true", help="不访问网络，只保存本地提取事件（用于自测）")
    parser.add_argument("--diagnostic", action="store_true", help="只显示监听回调摘要，不上传消息或调用模型")
    parser.add_argument("--poll", action="store_true", help="同时轮询指定群当前消息窗口，启动时建立不上传的本地基线")
    parser.add_argument("--once", action="store_true", help="扫描一次指定群的新消息，完成发送后自动退出")
    parser.add_argument("--retry-failed", action="store_true", help="把上次失败且保留在本机的事件重新发送")
    parser.add_argument(
        "--prompt-access-token",
        action="store_true",
        help="在本机终端隐藏输入 Worker 接口访问码；访问码不会进入命令参数或文件",
    )
    parser.add_argument("--self-test", action="store_true", help="运行消息规范化、筛选和去重自测后退出")
    return parser.parse_args()


def self_test() -> None:
    class FakeChat:
        who = DEFAULT_CHAT

        def ChatInfo(self):
            return {"nickname": DEFAULT_CHAT}

    good = {"type": "Text", "content": "老师：请于明天18:00前提交实验报告", "sender": "老师", "time": "2026-09-17T15:00:00+08:00"}
    ordinary = {"type": "Text", "content": "今天晚上一起吃饭吗", "sender": "同学", "time": "2026-09-17T15:01:00+08:00"}
    assert normalize_message(good, FakeChat(), DEFAULT_CHAT)["chat_name"] == DEFAULT_CHAT
    assert looks_like_task(good["content"])
    assert looks_like_task("明天有考试，请提前准备")
    assert not looks_like_task(ordinary["content"])
    assert normalize_message(good, FakeChat(), "另一个群") is None
    first = normalize_message(good, FakeChat(), DEFAULT_CHAT)
    second = normalize_message(good, FakeChat(), DEFAULT_CHAT)
    assert first["fingerprint"] == second["fingerprint"]
    print("self-test passed: text-only, exact-chat, task-filter and fingerprint dedupe")


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.chat.strip():
        print("请提供 --chat 或设置 WECHAT_CHAT_NAME。", file=sys.stderr)
        return 2
    access_token = os.environ.get("AI_ACCESS_TOKEN", "").strip()
    if args.prompt_access_token and not access_token:
        access_token = getpass.getpass("Worker 接口访问码（输入时不会显示）: ").strip()
        if not access_token:
            print("未输入 Worker 接口访问码，桥接未启动。", file=sys.stderr)
            return 2
    config = BridgeConfig(
        chat_name=args.chat.strip(),
        worker_url=args.worker_url,
        access_token=access_token,
        data_dir=args.data_dir,
        dry_run=args.dry_run or args.diagnostic,
        diagnostic=args.diagnostic,
        poll=args.poll,
        poll_once=args.once,
        retry_failed=args.retry_failed,
    )
    runner = BridgeRunner(config)
    signal.signal(signal.SIGINT, lambda *_: runner.stop.set())
    signal.signal(signal.SIGTERM, lambda *_: runner.stop.set())
    try:
        runner.start()
    except KeyboardInterrupt:
        runner.stop.set()
    except Exception as exc:
        print(f"[桥接未启动] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
