# HomeMind Air

HomeMind Air is a local, observe-first fresh-air decision hub for Home Assistant.
One container runs Mosquitto and the Python engine under s6-overlay. Home Assistant
WebSocket supplies live state and context; MQTT supplies discovery, recommendations,
feedback, availability, and the single guarded action channel.

## Safety state

Version `0.3.0` is an observe-only release. The Python service does not publish
action requests. Home Assistant's existing 900/700 ppm automations remain active.

The live deployment and rollback record is in [DEPLOYMENT.md](DEPLOYMENT.md).
Dynamic policy, audit export and remaining rollout work: [OBSERVATION-030.md](OBSERVATION-030.md).

## Persistent data

```text
/data/secrets/ha_token
/data/secrets/mqtt_password
/data/secrets/mosquitto.passwd
/data/secrets/mosquitto.acl
/data/ephemeris/de440s.bsp
/data/homemind-air.sqlite3
/data/health.json
```

Do not commit the contents of `/data/secrets`.

## Development

```bash
python3 -m pytest -q tests
docker buildx build --platform linux/amd64 --load -t homemind-air:0.3.0 .
```

## Rollout levels

- `observe`: entities and event records only; no notifications or actions.
- `recommend`: retained future approval mode; disabled in this release.
- `bounded_auto`: retained future automatic mode; disabled in this release.
