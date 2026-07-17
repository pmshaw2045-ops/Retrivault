#!/usr/bin/env python3
"""启动脚本：拉起 FastAPI 服务 + 打开浏览器前端。

用法：
    python scripts/start.py
或：
    make start
"""

import logging
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _log_subprocess_output(stream, logger):
    """在后台线程中持续消费子进程输出，防止 PIPE 满导致死锁"""
    for line in iter(stream.readline, ""):
        if line:
            logger.info(line.rstrip())
    stream.close()


def wait_for_service(url: str, timeout: int = 30) -> bool:
    """轮询等待服务就绪"""
    import httpx

    for _i in range(timeout):
        try:
            resp = httpx.get(url, timeout=1)
            if resp.status_code in (200, 404, 405):
                return True
        except (httpx.ConnectError, httpx.ReadTimeout):
            pass
        time.sleep(1)
    return False


def main():
    logger = logging.getLogger("retrivault")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(handler)

    project_root = Path(__file__).resolve().parent.parent
    python = sys.executable

    # 环境变量：绕过系统代理（macOS 用户常见卡点）
    env = os.environ.copy()
    env["NO_PROXY"] = "localhost,127.0.0.1"
    env["no_proxy"] = "localhost,127.0.0.1"

    print("🚀 启动 Retrivault RAG 系统...\n")

    # 1. 启动 FastAPI（后台）
    print("[1/2] 启动 API 服务 (port 8000)...")
    api = subprocess.Popen(
        [python, "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"],
        cwd=str(project_root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    # 后台线程消费输出，避免 PIPE 满死锁
    t = threading.Thread(target=_log_subprocess_output, args=(api.stdout, logger), daemon=True)
    t.start()

    if not wait_for_service("http://127.0.0.1:8000/api/health"):
        print("⚠️  API 启动超时，请检查日志。")
        api.kill()
        sys.exit(1)
    print("   ✅ API 就绪\n")

    # 2. 打开浏览器
    print("[2/2] 打开浏览器...")
    webbrowser.open("http://localhost:8000")

    print("""
╔══════════════════════════════════════════════╗
║  🧠 Retrivault — Obsidian RAG              ║
║                                              ║
║  前端  : http://localhost:8000               ║
║  API   : http://localhost:8000/api/status    ║
║  SSE   : http://localhost:8000/api/search/stream?q=测试 ║
║  评估  : http://localhost:8000/eval          ║
║                                              ║
║  按 Ctrl+C 停止服务                          ║
╚══════════════════════════════════════════════╝
""")

    try:
        api.wait()
    except KeyboardInterrupt:
        print("\n👋 停止服务...")
        api.terminate()
        api.wait()
        sys.exit(0)


if __name__ == "__main__":
    main()
