#!/usr/bin/env bash
# Launch the two Jobs. Needs `hf` (or `uvx hf`) logged in. About $0.01 total.
set -euo pipefail
cd "$(dirname "$0")"
BUCKET=${BUCKET:-$(hf auth whoami 2>/dev/null | grep -oE 'user=[^ ]+' | cut -d= -f2)/hf-mount-latency-repro}
TRIALS=${TRIALS:-3}
export HF_TOKEN=${HF_TOKEN:-$(hf auth token 2>/dev/null | tail -1)}

hf buckets create "${BUCKET#*/}" --private >/dev/null 2>&1 || true

WRITER=$(hf jobs run --detach --flavor cpu-basic --timeout 30m --expose 8000 \
    -v "hf://buckets/${BUCKET}:/lora" -v "$PWD:/work" \
    -- python:3.12 python /work/writer.py 2>&1 | grep -oE '[0-9a-f]{24}' | head -1)

READER=$(hf jobs run --detach --flavor cpu-basic --timeout 30m --secrets HF_TOKEN \
    -v "hf://buckets/${BUCKET}:/lora" -v "$PWD:/work" \
    -e "WRITER_URL=https://${WRITER}--8000.hf.jobs" -e "BUCKET=${BUCKET}" \
    -- python:3.12 python /work/reader.py "$TRIALS" 2>&1 | grep -oE '[0-9a-f]{24}' | head -1)

echo "writer $WRITER   reader $READER"
echo "hf jobs logs -f $READER"
echo "hf jobs cancel $WRITER; hf jobs cancel $READER    # when done"
