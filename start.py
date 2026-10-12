"""Start the local service workspace and stop only the processes created by this launcher."""

import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from contextlib import ExitStack

ROOT = Path(__file__).resolve().parent


def wait_ready(url, process):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Service exited before readiness. Check ./logs.")
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.3)
    raise RuntimeError(f"Service did not become ready: {url}. Check ./logs.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--frontend-port", type=int, default=3000)
    args = parser.parse_args()
    python = (
        ROOT
        / "backend"
        / ".venv"
        / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    next_bin = ROOT / "frontend/node_modules/next/dist/bin/next"
    node = shutil.which("node")
    if not python.exists() or not next_bin.exists() or not node:
        raise SystemExit(
            "Install backend/.venv requirements and frontend npm dependencies first. See README.md."
        )
    if args.backend_port == args.frontend_port or any(
        not 1024 <= p <= 65535 for p in (args.backend_port, args.frontend_port)
    ):
        raise SystemExit("Choose two distinct ports between 1024 and 65535.")
    for port in (args.backend_port, args.frontend_port):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                raise SystemExit(
                    f"Port {port} is in use; choose --backend-port / --frontend-port."
                )
        except OSError:
            pass
    env = {
        **os.environ,
        "BACKEND_URL": f"http://127.0.0.1:{args.backend_port}",
        "NEXT_DIST_DIR": f".next-serve-{args.frontend_port}",
        "PYTHONIOENCODING": "utf-8",
        "NEXT_TELEMETRY_DISABLED": "1",
    }
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    children = []
    with ExitStack() as stack:
        try:
            for name, command, cwd in [
                (
                    "backend",
                    [
                        str(python),
                        "-m",
                        "uvicorn",
                        "app.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(args.backend_port),
                    ],
                    ROOT / "backend",
                ),
                (
                    "frontend",
                    [
                        node,
                        str(next_bin),
                        "dev",
                        "--hostname",
                        "127.0.0.1",
                        "--port",
                        str(args.frontend_port),
                    ],
                    ROOT / "frontend",
                ),
            ]:
                output = stack.enter_context(
                    (logs / f"{name}.log").open("w", encoding="utf-8")
                )
                children.append(
                    subprocess.Popen(
                        command,
                        cwd=cwd,
                        env=env,
                        stdout=output,
                        stderr=subprocess.STDOUT,
                        creationflags=flags,
                    )
                )
            wait_ready(f"http://127.0.0.1:{args.backend_port}/api/health", children[0])
            wait_ready(f"http://127.0.0.1:{args.frontend_port}", children[1])
            wait_ready(f"http://127.0.0.1:{args.frontend_port}/api/health", children[1])
            print(f"AI customer service: http://127.0.0.1:{args.frontend_port}")
            print(f"API docs: http://127.0.0.1:{args.backend_port}/docs")
            input("Ready. Press Enter to stop these services.\n")
        except (KeyboardInterrupt, EOFError):
            pass
        finally:
            for process in reversed(children):
                if process.poll() is None:
                    if os.name == "nt":
                        subprocess.run(
                            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=flags,
                        )
                    else:
                        process.terminate()
                    process.wait(timeout=10)


if __name__ == "__main__":
    main()
