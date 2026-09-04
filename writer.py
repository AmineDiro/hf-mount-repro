"""Writer Job: on `POST /write?key=K`, write a fresh 4.7 MB random file to /lora/probe/K.bin and reply."""
import http.server, json, os, time, urllib.parse

MOUNT = os.environ.get("MOUNT", "/lora")


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # health check
        self._reply({"ok": True})

    def do_POST(self):
        key = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)["key"][0]
        os.makedirs(f"{MOUNT}/probe", exist_ok=True)
        t0 = time.monotonic()
        with open(f"{MOUNT}/probe/{key}.bin", "wb") as f:
            f.write(os.urandom(4_700_000))  # fresh bytes every time: Xet dedups identical content
            f.flush()
            os.fsync(f.fileno())
        self._reply({"key": key, "write_and_close_s": round(time.monotonic() - t0, 4)})

    def _reply(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


print("writer ready on :8000", flush=True)
http.server.HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
