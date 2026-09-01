#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mixed public proxy: keeps ONE ngrok URL (free plan limit) for two local
services:
  /rag/* and /search*  -> course RAG API   (127.0.0.1:8010)
  everything else      -> existing gateway (127.0.0.1:1340, llm-router)
Listens on :1359 (ngrok targets this port). Supports GET and POST (JSON body).
"""
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen

sys.stdout.reconfigure(encoding="utf-8")

RAG = "http://127.0.0.1:8010"
GATEWAY = "http://127.0.0.1:1340"


def fetch(base, path, qs="", method="GET", body=None, content_type="application/json"):
    url = f"{base}{path}" + (f"?{qs}" if qs else "")
    headers = {"User-Agent": "mix-proxy/1.0"}
    data = None
    if body is not None:
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        headers["Content-Type"] = content_type
    req = Request(url, headers=headers, data=data, method=method)
    try:
        with urlopen(req, timeout=300) as r:
            body_out = r.read()
            return r.status, dict(r.headers), body_out
    except Exception as e:  # noqa: BLE001
        detail = str(e)[:200]
        print(f"[mix-proxy] fetch error to {base}{path}: {detail}", flush=True)
        return 502, {"content-type": "application/json"}, detail.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def _do(self, body=None, content_type="application/json"):
        p = urllib.parse.urlparse(self.path)
        qs = p.query
        if p.path.startswith("/rag/"):
            target_path = p.path[len("/rag"):] or "/"
            status, headers, out = fetch(RAG, target_path, qs, self.command, body, content_type)
        elif p.path.startswith("/search") or p.path == "/docs":
            status, headers, out = fetch(RAG, p.path, qs, self.command, body, content_type)
        else:
            status, headers, out = fetch(GATEWAY, p.path, qs, self.command, body, content_type)
        print(f"[mix-proxy] {self.command} {p.path} qs={qs[:90]!r} -> {status} ({len(out)}b)", flush=True)
        self.send_response(status)
        ct = headers.get("content-type", "application/json")
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(out)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):  # noqa: N802
        self._do()

    def do_POST(self):  # noqa: N802
        ln = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(ln) if ln else None
        self._do(body, self.headers.get("Content-Type") or "application/json")

    def log_message(self, *args):  # noqa: A003
        pass


def main():
    port = 1359
    print(f"[mix-proxy] :{port} -> RAG(:8010) on /rag+ /search; else gateway(:1340)", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()