# onvif-cam-sim

Simulates a multi-channel ONVIF camera: a GStreamer-based RTSP server serving
synthetic video (live clock overlay + stream index) on multiple mount points,
each with an independently configurable simulated network quality (packet
loss, delay/jitter, duplication, bandwidth cap), plus a minimal ONVIF SOAP
server (Device + Media + Events services) and a WS-Discovery responder so
ONVIF clients/NVRs can discover and pull the streams, and a background
generator that fires simulated motion-detection events (human/vehicle/animal)
through a WS-BaseNotification PullPoint subscription.

## Requirements

- GStreamer 1.x with `gst-rtsp-server`, `gst-plugins-good` (x264enc/overlays)
  and `gst-plugins-bad` (the `netsim` element) installed system-wide, with
  Python `gi` bindings available (`PyGObject`).
- Python 3.12+, [`uv`](https://docs.astral.sh/uv/).

## Run

```sh
uv sync
uv run python3 main.py --config config.yaml
```

This starts:
- RTSP server on `rtsp://<host>:8554/streamN` (one per configured stream)
- ONVIF SOAP endpoints on `http://<host>:8080/onvif/device_service`,
  `/onvif/media_service`, and `/onvif/event_service`
- A WS-Discovery responder on UDP multicast `239.255.255.250:3702`
- A background motion-event generator feeding the Events PullPoint service

## Viewing a stream directly

```sh
ffplay rtsp://127.0.0.1:8554/stream0
# or
gst-launch-1.0 rtspsrc location=rtsp://127.0.0.1:8554/stream0 ! decodebin ! autovideosink
```

Each stream overlays a live clock (top-left) and `STREAM <index> - <name>`
(bottom-right) so streams are visually distinguishable.

## Talking to it as an ONVIF client

Point an ONVIF client/NVR at the host; it should discover the device via
WS-Discovery and be able to call `GetDeviceInformation`, `GetCapabilities`,
`GetProfiles`, and `GetStreamUri` against the device/media services to
retrieve each stream's RTSP URL. Manual example:

```sh
curl -X POST http://127.0.0.1:8080/onvif/media_service \
  -d '<?xml version="1.0"?><soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" xmlns:trt="http://www.onvif.org/ver10/media/wsdl"><soap:Body><trt:GetProfiles/></soap:Body></soap:Envelope>'
```

## Configuring streams and network quality

Edit `config.yaml`. Each entry under `streams` defines resolution, framerate,
bitrate, and a `network_profile`: one of the named presets under
`network_presets` (`perfect`, `good`, `poor`, `very_poor`), or `custom` with
an inline `custom_network` block. The knobs map directly onto GStreamer's
[`netsim`](https://gstreamer.freedesktop.org/documentation/netsim/) element,
inserted into each stream's pipeline before RTP payloading:

- `drop_probability` — probability an encoded frame is dropped (packet loss)
- `delay_probability`, `min_delay_ms`, `max_delay_ms` — jitter/latency
- `duplicate_probability` — frame duplication
- `max_kbps` — bandwidth cap (-1 = unlimited)

Note this simulates loss/jitter at the encoded-frame level (pre-payload),
not on raw UDP packets on the wire — it's meant for configurable stream
degradation, not bit-exact `netem` emulation.

Add or remove streams by editing the `streams` list; each gets its own RTSP
mount point at `/stream<index>` and its own ONVIF media profile
(`profile<index>`).

## Motion detection events

A background generator (`onvif_cam_sim/onvif/motion_events.py`) periodically
picks a random stream and object class, fires a `PropertyOperation="Changed"`
notification with the class's boolean field set `true`, waits a random
"active" duration, then fires it again `false` — simulating a motion event
starting and ending. Events are delivered through a minimal WS-BaseNotification
PullPoint implementation:

1. `POST /onvif/event_service` with `CreatePullPointSubscription` returns a
   per-subscription pull address at `/onvif/events/pullpoint/<id>`.
2. `POST` to that address with `PullMessages` (or `Renew`/`Unsubscribe`)
   drains that subscription's queued notifications.

Each of the three streams is a `<source>`; every active subscription receives
every event (there's no per-stream subscription filtering). Topics emitted:

| Class     | Topic                                      | Data field  |
|-----------|---------------------------------------------|-------------|
| human     | `tns1:RuleEngine/HumanDetector/Human`        | `IsHuman`   |
| vehicle   | `tns1:RuleEngine/VehicleDetector/Vehicle`    | `IsVehicle` |
| animal    | `tns1:RuleEngine/AnimalDetector/Animal`      | `IsAnimal`  |
| motion    | `tns1:RuleEngine/MotionDetector/Motion`      | `IsMotion`  |

Configure timing and which classes fire under the `events:` key in
`config.yaml` (`enabled`, `min_interval_s`/`max_interval_s` between events,
`active_duration_min_s`/`active_duration_max_s` for how long a detection stays
"true", and `classes` to restrict/reweight which object types occur).
