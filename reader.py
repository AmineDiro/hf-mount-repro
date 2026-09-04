"""Reader Job: how long after the writer's close() returns does the file appear on THIS Job's hf-mount?

Two modes, alternated:
  cold   open() the path every 0.25 s starting right away          -> ~30 s
  gated  first ask the Hub API whether the file exists, only then   -> ~2.5 s, first open() succeeds
         open() it (the mount is never touched before the upload landed)
"""
import json, os, sys, time, urllib.parse, urllib.request

MOUNT = os.environ.get("MOUNT", "/lora")
WRITER, BUCKET = os.environ["WRITER_URL"], os.environ["BUCKET"]
HEADERS = {"Authorization": f"Bearer {os.environ['HF_TOKEN']}"}  # the jobs proxy needs it; so does the Hub API


def http(method, url, data=None):
    with urllib.request.urlopen(urllib.request.Request(url, method=method, data=data, headers=HEADERS), timeout=300) as r:
        return json.loads(r.read())


def on_hub(path):  # ask the Hub directly, bypassing the mount
    body = urllib.parse.urlencode({"paths": path}).encode()
    return len(http("POST", f"https://huggingface.co/api/buckets/{BUCKET}/paths-info", body)) > 0


def on_mount(path):
    try:
        open(path, "rb").close()
        return True
    except FileNotFoundError:
        return False


def trial(mode):
    key = f"{mode}-{int(time.time())}"
    http("POST", f"{WRITER}/write?key={key}")  # returns once the writer's close() has returned
    t0 = time.monotonic()
    t_hub = first_open_ok = None
    if mode == "gated":
        while not on_hub(f"probe/{key}.bin"):
            time.sleep(0.25)
        t_hub = time.monotonic() - t0
        first_open_ok = on_mount(f"{MOUNT}/probe/{key}.bin")
    while not on_mount(f"{MOUNT}/probe/{key}.bin"):
        time.sleep(0.25)
    t_mount = time.monotonic() - t0
    hub = "  n/a " if t_hub is None else f"{t_hub:5.2f}s"
    ok = "  n/a" if first_open_ok is None else str(first_open_ok)
    print(f"{mode:5}  on Hub after {hub}   on this mount after {t_mount:5.2f}s   first open() ok: {ok}", flush=True)


for attempt in range(60):  # wait for the writer to come up
    try:
        http("GET", WRITER)
        break
    except Exception:
        time.sleep(5)

for _ in range(int(sys.argv[1]) if len(sys.argv) > 1 else 3):
    trial("cold")
    trial("gated")
