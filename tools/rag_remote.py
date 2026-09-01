#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Remote RAG search for agents: queries a remote RAG API
(via the public ngrok URL, or FALT_RAG_URL override).

Usage:
  python tools/rag_remote.py "Ньютон законы движения" [-k 5] [--topic history_of_physics] [--json]
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))


def default_url():
    urlfile = os.path.join(HERE, "..", "server", "ngrok-url.txt")
    if os.path.exists(urlfile):
        return open(urlfile, encoding="utf-8").read().strip()
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("q")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--topic", default=None)
    ap.add_argument("--threshold", type=float, default=0.0)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--url", default=os.environ.get("FALT_RAG_URL") or default_url())
    a = ap.parse_args()
    if not a.url:
        sys.stderr.write("[tools] Укажите FALT_RAG_URL или создайте server/ngrok-url.txt\n"
                         "(шаблон: server/ngrok-url.example.txt; см. docs/REMOTE-RAG.md)\n")
        return 2

    qs = urllib.parse.urlencode({"q": a.q, "k": a.k})
    if a.topic:
        qs += "&topic=" + urllib.parse.quote(a.topic)
    if a.threshold:
        qs += "&threshold=" + str(a.threshold)
    url = f"{a.url}/rag/search?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "falt-rag-remote/1.0",
                                               "ngrok-skip-browser-warning": "1"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode("utf-8"))
    if a.json:
        print(json.dumps(data, ensure_ascii=False, indent=1))
        return 0
    print(f"query: {data['query']} | count: {data['count']}")
    for res in data["results"]:
        print(f"  {res['score']:.3f} | {res['file']} | фрагмент #{res['chunk_id']}")
        print(f"    {res['snippet'][:110]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())