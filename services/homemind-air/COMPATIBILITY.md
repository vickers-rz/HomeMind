# Home Assistant compatibility fixes

## Scope

These local fixes are required because the installed releases are already the
latest stable versions (`xiaomi_home` v0.4.7 and `xiaomi_miot` v1.1.4), while
their Home Assistant 2026/2027 compatibility work has not yet shipped in a
stable release.

## Xiaomi Home

Applied the entity-ID compatibility design from upstream PR
[`XiaoMi/ha_xiaomi_home#1639`](https://github.com/XiaoMi/ha_xiaomi_home/pull/1639):

- Keep existing integration-domain unique IDs for registry continuity.
- Generate runtime entity IDs with the actual HA platform domain.
- Slugify MIoT service descriptions before assigning an entity ID.
- Migrate unique IDs from earlier unofficial formats without renaming the user's
  existing registered entity IDs.

The upstream diff is retained as
`patches/xiaomi-home-ha-2026-entity-id-compat.patch`.

Added a device-spec correction for
`urn:miot-spec-v2:device:air-conditioner:0000A004:xiaomi-r24r00:4`, property
`10.6` (`humidity-range`): its unit is `none`, because the device reports a
text range such as `40-70`, not a numeric percentage. The patch is retained as
`patches/xiaomi-r24r00-humidity-range.patch`.

Replaced deprecated concentration constants with `UnitOfDensity` and
`UnitOfRatio`. Device tracker battery and area metadata now use extra state
attributes instead of overriding tracker APIs scheduled for removal in HA
2027.7.

## Xiaomi Miot

The installed v1.1.4 remains the stable release used for the local fresh-air
entity. Applied the equivalent changes already present in the project's current
master branch for `device_tracker.py`:

- Import tracker classes from `homeassistant.components.device_tracker`.
- Stop overriding removed `battery_level` and `location_name` properties.
- Preserve address information as an ordinary attribute.

Replaced deprecated concentration constants in `core/miot_spec.py` with
`UnitOfDensity`, `UnitOfRatio`, and the literal `p/m³` unit requested by HA.

## Upgrade procedure

HACS upgrades may overwrite these files. Before upgrading either integration:

1. Keep the two rollback bundles listed in `DEPLOYMENT.md`.
2. Check whether the stable release includes the upstream fixes.
3. Upgrade normally if it does, then remove only patches made redundant upstream.
4. Run Python compilation and HA `check_config` before restarting.
5. Review startup logs for entity-domain, humidity-range, unit, and tracker warnings.

Do not blindly reapply these patches to a newer source tree; compare upstream
first, because unique-ID migration code must remain aligned with the released
integration.
