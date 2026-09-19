#!/bin/sh
set -eu

HOMEMIND_DATA_DIR="${HOMEMIND_DATA_DIR:-/opt/homemind-air/data}"

docker run -d \
  --name homemind-air-learner \
  --restart unless-stopped \
  --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=128m \
  --memory 768m \
  --cpus 1.0 \
  --pids-limit 128 \
  --log-driver json-file --log-opt max-size=10m --log-opt max-file=3 \
  --security-opt no-new-privileges:true \
  --cap-drop ALL \
  -e TZ=Asia/Shanghai \
  -e LOOKBACK_DAYS=30 \
  -e LEARN_INTERVAL_SECONDS=900 \
  -e OMP_NUM_THREADS=1 \
  -e OPENBLAS_NUM_THREADS=1 \
  -e MKL_NUM_THREADS=1 \
  -v "$HOMEMIND_DATA_DIR:/data" \
  homemind-air-learner:0.1.0
