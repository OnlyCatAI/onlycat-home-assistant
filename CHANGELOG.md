# Changelog

## v2.0.7
### Changes
- Use `getDeviceRebootLogs` instead of `getDeviceErrorLogs` as api changed
- Switch terminology from `account token` to `api key` as indicated by the app
- Deregister listeners on unload/reload to prevent `hass is None` errors
- Use `eventSummary` updates for event sensor to catch all events
### Breaking changes
- Due to the change to `eventSummary` the event sensor now changes state per summary subevent containing only one `RfidCode` at a time. The `RfidCodes` list still exists if a full event is received.
`RfidCode` should be  the source of truth for automations.
- The `errors` attribute on the device-errors sensor changes shape: `{deviceId, timestamp, build, cause, isError, summary, detail, message}` instead of `{time, deviceId, measureName, message}`.
### Update dependencies
- Bump hassfest validation
- Bump development dependencies
---

## v2.0.6
### Update dependencies
- Bump actions/checkout from 6.0.3 to 7.0.1 (#74)
- Bump colorlog from 6.10.1 to 6.11.0 (#73)
- Bump actions/setup-python from 6.2.0 to 7.0.0 (#72)
- Bump ruff from 0.15.17 to 0.15.22 (#71)
- Bump home-assistant/actions/hassfest (#68)
- Bump pytest from 9.1.0 to 9.1.1 (#64)
- Bump python-socketio from 5.16.2 to 5.16.3 (#61)
- Bump pytest-asyncio from 1.3.0 to 1.4.0 (#52)
### Improve device tracker and pet status reliability
- Persist device_tracker and pet status across reloads/restarts using the most recent datapoint (#167)
- Update device_trackers to in_zones (#169)
### Update schema
- Add activatedAt field to schema (#166)
- Add empty string to schema for activation sounds (#168)
---

## v2.0.5
### Update dependencies
- Bump pytest-asyncio from 1.3.0 to 1.4.0 (#142)
- Bump actions/checkout from 6.0.2 to 6.0.3 (#141)
- Bump home-assistant/actions (#146)
- Bump pytest from 9.0.3 to 9.1.0 (#148)
- Bump python-socketio from 5.16.2 to 5.16.3 (#149)
### Reduce errors on camera stream and event summaries
- Stream Validation & Bug Fixes (#137)
---

## v2.0.4
### Update to HA 2026.5.3
- Introduce release mechanism and versioning
- Update test dependencies
- Fix translations on setup screen
---

