#!/bin/sh
set -eu

if [ "$(id -u)" = "0" ]; then
  exec /command/s6-setuidgid homemind "$0"
fi

password="$(cat "${MQTT_PASSWORD_FILE:-/data/secrets/mqtt_password}")"
mosquitto_pub -h 127.0.0.1 -u "${MQTT_USERNAME:-homemind}" -P "$password" \
  -t homemind/air/v1/internal/health -m "$(date +%s)" -q 1

test -s /data/health.json
now="$(date +%s)"
updated="$(stat -c %Y /data/health.json)"
test $((now - updated)) -lt 120

python3 - <<'PY'
import json
import sqlite3
from datetime import datetime, timezone

with open('/data/health.json', encoding='utf-8') as handle:
    health = json.load(handle)
assert health.get('ha_connected') is True
assert int(health.get('ha_state_count', 0)) > 0
assert (datetime.now(timezone.utc) - datetime.fromisoformat(health['last_ha_message_at'])).total_seconds() < 90

with sqlite3.connect('/data/homemind-air.sqlite3') as db:
    db.execute('BEGIN IMMEDIATE')
    db.execute('ROLLBACK')
PY
