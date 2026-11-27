"""Serves the country feeds at /feeds/<cc>.tsv and rebuilds them every few hours."""
import json
import os
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from feeds import COUNTRIES, build_feed

REFRESH_HOURS = float(os.environ.get("REFRESH_HOURS", "4"))
ENABLED = [c.strip() for c in os.environ.get("FEED_COUNTRIES", ",".join(COUNTRIES)).split(",") if c.strip() in COUNTRIES]

FEEDS = {}   # cc -> bytes
STATUS = {}  # cc -> dict
LOCK = threading.Lock()


def refresh_all():
    for cc in ENABLED:
        started = time.time()
        try:
            text, stats = build_feed(cc)
            if stats["items"] == 0:
                raise RuntimeError("feed came back empty; keeping the previous file")
            with LOCK:
                FEEDS[cc] = text.encode("utf-8")
                STATUS[cc] = {"ok": True, **stats, "built_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                              "seconds": round(time.time() - started, 1)}
            print(f"[feed] {cc}: {stats}", flush=True)
        except Exception as e:  # keep serving the last good feed
            with LOCK:
                prev = STATUS.get(cc, {})
                STATUS[cc] = {**prev, "ok": False, "error": str(e)[:300],
                              "failed_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())}
            print(f"[feed] {cc} FAILED: {e}", flush=True)
            traceback.print_exc()
        time.sleep(3)


def loop():
    while True:
        refresh_all()
        time.sleep(REFRESH_HOURS * 3600)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path in ("", "/health", "/status"):
            with LOCK:
                body = json.dumps({"countries": ENABLED, "refresh_hours": REFRESH_HOURS, "feeds": STATUS}, indent=2)
            return self._send(200, body.encode(), "application/json")
        if path.startswith("/feeds/") and path.endswith(".tsv"):
            cc = path[len("/feeds/"):-4].lower()
            with LOCK:
                data = FEEDS.get(cc)
            if data is None:
                return self._send(503 if cc in ENABLED else 404, b"feed not ready", "text/plain")
            return self._send(200, data, "text/tab-separated-values; charset=utf-8")
        return self._send(404, b"not found", "text/plain")

    def log_message(self, fmt, *args):
        print("[http] " + fmt % args, flush=True)


if __name__ == "__main__":
    threading.Thread(target=loop, daemon=True).start()
    port = int(os.environ.get("PORT", "10000"))
    print(f"[server] listening on {port}; countries={ENABLED}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
