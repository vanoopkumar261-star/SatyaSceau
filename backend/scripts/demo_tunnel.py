"""One command for demo readiness: public tunnel + BASE_URL + fresh QR.  Owner: Pile 1 (Platform).

Run from backend/ while the server is running:
    python scripts/demo_tunnel.py              # Ctrl+C stops the tunnel

It starts a Cloudflare quick tunnel to localhost (over HTTP/2: many campus networks block QUIC),
writes the new https://....trycloudflare.com URL into backend/.env as BASE_URL, and re-runs
seed_demo.py so the printed QR poster points at it. Quick-tunnel URLs change on every start.

The server reads BASE_URL from .env live, so it does NOT need a restart after this.
"""

import argparse
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def find_cloudflared(explicit: str | None) -> str:
    candidates = [explicit] if explicit else []
    candidates += [str(REPO / "tools" / "cloudflared.exe"), str(REPO / "tools" / "cloudflared"), shutil.which("cloudflared")]
    for c in candidates:
        if c and Path(c).exists():
            return c
    sys.exit("cloudflared not found. Put cloudflared.exe in tools/ (see README 'Demo') or pass --cloudflared PATH.")


def set_base_url(url: str, env_path: Path = BACKEND / ".env") -> None:
    """Write BASE_URL into backend/.env (created from .env.example if missing), keeping other lines."""
    if not env_path.exists():
        example = BACKEND / ".env.example"
        env_path.write_text(example.read_text(encoding="utf-8") if example.exists() else "", encoding="utf-8")
    text = env_path.read_text(encoding="utf-8")
    if re.search(r"(?m)^BASE_URL=", text):
        text = re.sub(r"(?m)^BASE_URL=.*$", f"BASE_URL={url}", text)
    else:
        text = text.rstrip("\n") + f"\nBASE_URL={url}\n"
    env_path.write_text(text, encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Start the demo tunnel and point BASE_URL + QR at it.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--cloudflared", help="path to cloudflared(.exe)")
    parser.add_argument("--timeout", type=int, default=45, help="seconds to wait for the tunnel")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    exe = find_cloudflared(args.cloudflared)
    cmd = [exe, "tunnel", "--no-autoupdate", "--protocol", "http2", "--url", f"http://localhost:{args.port}"]
    print("Starting tunnel:", " ".join(cmd))
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")

    found = {"url": None, "ready": False}
    errors: list[str] = []

    def pump():  # always drain cloudflared's output, or its pipe fills up and it stalls
        for line in proc.stdout:
            if not found["url"] and (m := URL_RE.search(line)):
                found["url"] = m.group(0)
            if "Registered tunnel connection" in line:
                found["ready"] = True
            if " ERR " in line:
                errors.append(line.strip())
                if found["ready"]:
                    print("  cloudflared:", line.strip())

    threading.Thread(target=pump, daemon=True).start()
    deadline = time.time() + args.timeout
    while time.time() < deadline and not (found["url"] and found["ready"]) and proc.poll() is None:
        time.sleep(0.2)

    if not (found["url"] and found["ready"]):
        proc.terminate()
        print("Tunnel did not come up in time.", *errors[-3:], sep="\n  ")
        return 1

    url = found["url"]
    set_base_url(url)
    print(f"\nTunnel up: {url}\nBASE_URL written to backend/.env")

    sys.path.insert(0, str(BACKEND))
    from scripts import seed_demo  # imported late: settings are read at import time
    seed_demo.main(["--base-url", url, "--port", str(args.port)])

    print("Tunnel running. Press Ctrl+C to stop.")
    try:
        while proc.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
