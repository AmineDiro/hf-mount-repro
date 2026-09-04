# hf-mount: a new file takes ~30 s to appear on another Job's mount, the upload takes ~2.5 s

Two HF Jobs mount the same Storage Bucket at `/lora`. One writes a 4.7 MB file. The other measures how long until
it can `open()` that file. Everything is timed on the reader's clock, starting when the writer's `close()` has
returned.

| what the reader does | file visible after |
|---|---|
| `open()` the path every 0.25 s, starting immediately (`cold`) | **~30 s** (13 to 30 s) |
| ask the Hub API until the file exists (~2.5 s), *then* `open()` once (`gated`) | **~2.6 s**, first `open()` succeeds |

So the upload lands in ~2.5 s. The other 27 s is the reader's mount serving a cached "no such file" that it took
*before* the upload landed. Payload size does not matter (same 30 s from 1 KB to 128 MiB), and neither does
`listdir` vs `open`, rename vs direct write, or re-listing the parent every 0.5 s. Only "did the first lookup happen
before or after the upload landed" matters.

## Files

- `writer.py` (30 lines): HTTP server on an exposed port, writes a fresh random file into the mount on request.
- `reader.py` (59 lines): alternates `cold` and `gated` trials, prints one line each.
- `run.sh`: launches both as `cpu-basic` Jobs (about $0.01 total).

Both scripts are stdlib only and run on the bare `python:3.12` image.

## Run

```sh
hf auth login            # once; or use `uvx hf` everywhere below
./run.sh                 # creates bucket <you>/hf-mount-latency-repro, starts writer then reader
hf jobs logs -f <reader id>
```

Output of the run on 2026-09-04 (Jobs `6a9aaf99259f8e97255de3df` / `6a9aaf9a259f8e97255de3e1`, both `cpu-basic`,
mount line `hf-mount /lora fuse rw,nosuid,nodev,relatime,idmapped,user_id=0,group_id=0,default_permissions,allow_other`):

```
cold   on Hub after   n/a    on this mount after 27.89s   first open() ok:   n/a
gated  on Hub after  2.55s   on this mount after  2.58s   first open() ok: True
cold   on Hub after   n/a    on this mount after 27.36s   first open() ok:   n/a
gated  on Hub after  2.49s   on this mount after  2.52s   first open() ok: True
cold   on Hub after   n/a    on this mount after 27.59s   first open() ok:   n/a
gated  on Hub after  2.52s   on this mount after  2.54s   first open() ok: True
```

Then `hf jobs cancel <writer id>` and `hf jobs cancel <reader id>`; the writer bills until its 30 min timeout otherwise.

### By hand, without `run.sh`

```sh
export HF_TOKEN=$(hf auth token | tail -1)
BUCKET=<you>/hf-mount-latency-repro
hf buckets create hf-mount-latency-repro --private

WRITER=$(hf jobs run --detach --flavor cpu-basic --timeout 30m --expose 8000 \
    -v hf://buckets/$BUCKET:/lora -v $PWD:/work -- python:3.12 python /work/writer.py | grep -oE '[0-9a-f]{24}' | head -1)

hf jobs run --flavor cpu-basic --timeout 30m --secrets HF_TOKEN \
    -v hf://buckets/$BUCKET:/lora -v $PWD:/work \
    -e WRITER_URL=https://${WRITER}--8000.hf.jobs -e BUCKET=$BUCKET -- python:3.12 python /work/reader.py 3
```

Notes: the exposed port requires `Authorization: Bearer $HF_TOKEN`, hence `--secrets HF_TOKEN` on the reader.
`-v $PWD:/work` syncs this directory to your `jobs-artifacts` bucket and mounts it read-only.

## What the reader measures, precisely

1. `POST /write?key=K` to the writer. The writer does `open / write 4.7 MB of os.urandom / flush / fsync / close`
   and replies. That whole sequence takes < 0.1 s: the mount acknowledges the write before uploading.
2. Reader starts its stopwatch when the reply arrives.
3. `cold`: `open("/lora/probe/K.bin")` every 0.25 s until it succeeds.
   `gated`: `POST /api/buckets/<bucket>/paths-info` every 0.25 s until the Hub lists `probe/K.bin`, then `open()`.

The fresh random payload per trial matters: Xet deduplicates, so re-writing the same bytes would not measure an upload.

## Why it matters

Any two-Job pipeline that hands files across a bucket (here: a trainer publishing LoRA adapters that a vLLM Job
loads by path) and polls the mount for the new path pays ~30 s per hand-off, while the data was there after 2.5 s.
The `hf-mount` README describes a 10 s metadata TTL; for paths that did not exist at first lookup we measure 30 s,
which matches the background poll interval instead.
