**hf-mount in Jobs: a new file takes ~30 s to appear on another Job's mount; the upload itself takes 2.5 s**

- 2 cpu-basic Jobs, same bucket mounted rw at `/lora`. A writes a 4.7 MB file, B times until `open()` works, on B's clock from A's `close()` return. 135 trials.
- A's `write+fsync+close` returns in <0.1 s (upload is async). The Hub API lists the file after **2.5 s**. B's mount sees it after **~30 s** (p50 29.9). Same from 1 KB to 128 MiB; `listdir`/`open`, rename/direct, re-listing the parent: no effect.
- Cause, measured: B's first `open()` happens before the upload landed and that "not found" is served for ~30 s. If B's *first* `open()` comes after the Hub lists the file, it succeeds immediately (20/20, 2.6 s total). `listdir` of the parent stays stale even then.
- README says ~10 s metadata TTL; for not-yet-existing paths it is 30 s (the poll interval), and neither knob is exposed on Jobs volumes.
- Impact: any producer→consumer hand-off through a mounted bucket (our trainer → vLLM LoRA sync) pays 30 s instead of 2.5 s.
- Minimal repro, 2 stdlib scripts, ~$0.01: <gist link>
