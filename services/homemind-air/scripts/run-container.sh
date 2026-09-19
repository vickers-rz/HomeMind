#!/bin/sh
set -eu

HOMEMIND_DATA_DIR="${HOMEMIND_DATA_DIR:-/opt/homemind-air/data}"

docker run -d \
  --name homemind-air \
  --network host \
  --restart unless-stopped \
  --stop-timeout 30 \
  --read-only \
  --tmpfs /run:rw,exec,nosuid,nodev,size=16m \
  --tmpfs /tmp:rw,nosuid,nodev,size=32m \
  --memory 512m \
  --cpus 1.0 \
  --pids-limit 128 \
  --log-driver json-file --log-opt max-size=10m --log-opt max-file=3 \
  --security-opt no-new-privileges:true \
  --cap-drop ALL \
  --cap-add SETUID \
  --cap-add SETGID \
  --cap-add KILL \
  -e TZ=Asia/Shanghai \
  -e CLIMATE_PROFILE=xian_cold_monsoon \
  -e MQTT_USERNAME=homemind \
  -e MQTT_PASSWORD_FILE=/data/secrets/mqtt_password \
  -v "$HOMEMIND_DATA_DIR:/data" \
  homemind-air:0.5.1
