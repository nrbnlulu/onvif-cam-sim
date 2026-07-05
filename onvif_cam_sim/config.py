"""YAML config loading for the ONVIF camera simulator."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from onvif_cam_sim.network_profiles import NETWORK_PRESETS, NetworkProfile


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    rtsp_port: int = 8554
    http_port: int = 8080
    device_name: str = "Simulated ONVIF Camera"
    manufacturer: str = "onvif-cam-sim"


@dataclass
class StreamConfig:
    index: int
    name: str
    width: int
    height: int
    framerate: int
    bitrate_kbps: int
    network: NetworkProfile

    @property
    def mount_path(self) -> str:
        return f"/stream{self.index}"


@dataclass
class EventsConfig:
    enabled: bool = True
    min_interval_s: float = 5.0
    max_interval_s: float = 15.0
    active_duration_min_s: float = 2.0
    active_duration_max_s: float = 6.0
    classes: list[str] = field(default_factory=lambda: ["human", "vehicle", "animal", "motion"])


@dataclass
class AppConfig:
    server: ServerConfig = field(default_factory=ServerConfig)
    streams: list[StreamConfig] = field(default_factory=list)
    events: EventsConfig = field(default_factory=EventsConfig)


def _resolve_network(stream_dict: dict, presets: dict[str, NetworkProfile]) -> NetworkProfile:
    profile_name = stream_dict.get("network_profile", "perfect")
    if profile_name == "custom":
        custom = stream_dict.get("custom_network") or {}
        return NetworkProfile(
            drop_probability=custom.get("drop_probability", 0.0),
            delay_probability=custom.get("delay_probability", 0.0),
            min_delay_ms=custom.get("min_delay_ms", 0),
            max_delay_ms=custom.get("max_delay_ms", 0),
            duplicate_probability=custom.get("duplicate_probability", 0.0),
            max_kbps=custom.get("max_kbps", -1),
        )
    try:
        return presets[profile_name]
    except KeyError:
        raise ValueError(
            f"Unknown network_profile {profile_name!r} for stream {stream_dict.get('name')!r}; "
            f"expected one of {sorted(presets)} or 'custom'"
        ) from None


def load_config(path: str | Path) -> AppConfig:
    raw = yaml.safe_load(Path(path).read_text())

    presets = dict(NETWORK_PRESETS)
    for name, values in (raw.get("network_presets") or {}).items():
        presets[name] = NetworkProfile(
            drop_probability=values.get("drop_probability", 0.0),
            delay_probability=values.get("delay_probability", 0.0),
            min_delay_ms=values.get("min_delay_ms", 0),
            max_delay_ms=values.get("max_delay_ms", 0),
            duplicate_probability=values.get("duplicate_probability", 0.0),
            max_kbps=values.get("max_kbps", -1),
        )

    server_dict = raw.get("server") or {}
    server = ServerConfig(
        host=server_dict.get("host", ServerConfig.host),
        rtsp_port=server_dict.get("rtsp_port", ServerConfig.rtsp_port),
        http_port=server_dict.get("http_port", ServerConfig.http_port),
        device_name=server_dict.get("device_name", ServerConfig.device_name),
        manufacturer=server_dict.get("manufacturer", ServerConfig.manufacturer),
    )

    streams = [
        StreamConfig(
            index=s["index"],
            name=s["name"],
            width=s["width"],
            height=s["height"],
            framerate=s["framerate"],
            bitrate_kbps=s["bitrate_kbps"],
            network=_resolve_network(s, presets),
        )
        for s in raw.get("streams") or []
    ]

    events_dict = raw.get("events") or {}
    events = EventsConfig(
        enabled=events_dict.get("enabled", EventsConfig.enabled),
        min_interval_s=events_dict.get("min_interval_s", EventsConfig.min_interval_s),
        max_interval_s=events_dict.get("max_interval_s", EventsConfig.max_interval_s),
        active_duration_min_s=events_dict.get(
            "active_duration_min_s", EventsConfig.active_duration_min_s
        ),
        active_duration_max_s=events_dict.get(
            "active_duration_max_s", EventsConfig.active_duration_max_s
        ),
        classes=events_dict.get("classes", ["human", "vehicle", "animal", "motion"]),
    )

    return AppConfig(server=server, streams=streams, events=events)
