"""Rotate the Worker access code securely, then start the local bridge.

The code is entered with echo disabled, sent to Wrangler over stdin, and kept
only in this process while the bridge runs.  It is never placed in a command
argument, source file, log, or repository state.
"""

from __future__ import annotations

import getpass
import os
import signal
import subprocess
import sys
from pathlib import Path

import bridge


PROJECT_ROOT = Path(__file__).resolve().parent.parent
WRANGLER_CONFIG = PROJECT_ROOT / "wrangler.jsonc"
RUNTIME_ROOT = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies"
PNPM = RUNTIME_ROOT / "bin" / "fallback" / "pnpm.cmd"
NODE_BIN = RUNTIME_ROOT / "node" / "bin"


def read_new_code() -> str:
    for _ in range(3):
        first = getpass.getpass("设置新的 Worker 接口访问码（输入时不会显示）: ").strip()
        if len(first) < 8:
            print("访问码至少需要 8 个字符，请重新输入。", file=sys.stderr)
            continue
        second = getpass.getpass("再次输入同一个访问码: ").strip()
        if first == second:
            return first
        print("两次输入不一致，请重新输入。", file=sys.stderr)
    raise RuntimeError("连续三次未能确认访问码，未修改 Cloudflare 配置。")


def put_secret(value: str) -> None:
    if not WRANGLER_CONFIG.is_file():
        raise RuntimeError(f"找不到 Worker 配置：{WRANGLER_CONFIG}")
    if not PNPM.is_file() or not (NODE_BIN / "node.exe").is_file():
        raise RuntimeError("找不到本机 Wrangler 运行环境。")
    environment = os.environ.copy()
    environment["PATH"] = str(NODE_BIN) + os.pathsep + environment.get("PATH", "")
    command = [
        environment.get("COMSPEC", r"C:\Windows\System32\cmd.exe"),
        "/d",
        "/c",
        str(PNPM),
        "dlx",
        "wrangler@latest",
        "secret",
        "put",
        "AI_ACCESS_TOKEN",
        "--config",
        str(WRANGLER_CONFIG),
    ]
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=environment,
        input=value + "\n",
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("Cloudflare 访问码更新失败；旧访问码保持不变。")


def main() -> int:
    try:
        access_code = read_new_code()
        print("正在安全更新 Cloudflare Worker 访问码……", flush=True)
        put_secret(access_code)
        print("[ACCESS_CODE_UPDATED] 新访问码已生效，正在启动微信桥接……", flush=True)
        config = bridge.BridgeConfig(
            chat_name=bridge.DEFAULT_CHAT,
            worker_url=bridge.DEFAULT_WORKER,
            access_token=access_code,
            data_dir=bridge.default_data_dir(),
            poll=True,
        )
        runner = bridge.BridgeRunner(config)
        signal.signal(signal.SIGINT, lambda *_: runner.stop.set())
        signal.signal(signal.SIGTERM, lambda *_: runner.stop.set())
        runner.start()
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"[未完成] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
