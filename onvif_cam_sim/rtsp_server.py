"""GStreamer RTSP server: one mount point per configured fake stream."""

from __future__ import annotations

import logging
import threading

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstRtspServer", "1.0")
from gi.repository import GLib, Gst, GstRtspServer  # noqa: E402

from onvif_cam_sim.config import AppConfig, StreamConfig

logger = logging.getLogger(__name__)

_TEST_PATTERNS = ["smpte", "ball", "snow", "bar"]


def _pattern_for_index(index: int) -> str:
    return _TEST_PATTERNS[index % len(_TEST_PATTERNS)]


def _escape_overlay_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def build_launch_string(stream: StreamConfig) -> str:
    overlay_text = _escape_overlay_text(f"STREAM {stream.index} - {stream.name}")
    pattern = _pattern_for_index(stream.index)

    pipeline = (
        f"videotestsrc pattern={pattern} is-live=true ! "
        f"video/x-raw,width={stream.width},height={stream.height},framerate={stream.framerate}/1 ! "
        f'clockoverlay time-format="%Y-%m-%d %H:%M:%S" halignment=left valignment=top '
        f"font-desc=\"Sans 16\" ! "
        f'textoverlay text="{overlay_text}" halignment=right valignment=bottom '
        f"font-desc=\"Sans 20\" ! "
        f"videoconvert ! "
        f"x264enc tune=zerolatency speed-preset=ultrafast "
        f"bitrate={stream.bitrate_kbps} key-int-max=30 ! "
        f"h264parse ! "
    )

    if not stream.network.is_perfect:
        props = stream.network.to_netsim_properties()
        netsim_args = " ".join(f"{key}={value}" for key, value in props.items())
        pipeline += f"netsim {netsim_args} ! "

    pipeline += "rtph264pay name=pay0 pt=96"
    return pipeline


class OnvifSimRtspServer:
    """Wraps GstRtspServer.RTSPServer, one mount point per stream, running its own GLib loop."""

    def __init__(self, config: AppConfig):
        self._config = config
        self._loop: GLib.MainLoop | None = None
        self._thread: threading.Thread | None = None
        self._server: GstRtspServer.RTSPServer | None = None

    def start(self) -> None:
        Gst.init(None)

        self._server = GstRtspServer.RTSPServer()
        self._server.set_service(str(self._config.server.rtsp_port))
        self._server.set_address(self._config.server.host)

        mounts = self._server.get_mount_points()
        for stream in self._config.streams:
            factory = GstRtspServer.RTSPMediaFactory()
            factory.set_launch(build_launch_string(stream))
            factory.set_shared(True)
            mounts.add_factory(stream.mount_path, factory)
            logger.info(
                "RTSP mount %s -> stream %r (%dx%d@%d, network=%s)",
                stream.mount_path,
                stream.name,
                stream.width,
                stream.height,
                stream.framerate,
                "perfect" if stream.network.is_perfect else "impaired",
            )

        self._loop = GLib.MainLoop()
        attach_id = self._server.attach(None)
        if attach_id == 0:
            raise RuntimeError(
                f"Failed to bind RTSP server to "
                f"{self._config.server.host}:{self._config.server.rtsp_port}"
            )

        self._thread = threading.Thread(target=self._loop.run, name="gst-rtsp-loop", daemon=True)
        self._thread.start()
        logger.info(
            "RTSP server listening on rtsp://%s:%d/",
            self._config.server.host,
            self._config.server.rtsp_port,
        )

    def stop(self) -> None:
        if self._loop is not None:
            self._loop.quit()
        if self._thread is not None:
            self._thread.join(timeout=5)
