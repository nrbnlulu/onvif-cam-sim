"""Wires config -> RTSP server + ONVIF SOAP app + WS-Discovery responder."""

from __future__ import annotations

import asyncio
import logging
import socket
import uuid

from aiohttp import web

from onvif_cam_sim.config import AppConfig, load_config
from onvif_cam_sim.onvif.device_service import make_device_service_handler
from onvif_cam_sim.onvif.discovery import start_discovery_responder
from onvif_cam_sim.onvif.media_service import make_media_service_handler
from onvif_cam_sim.rtsp_server import OnvifSimRtspServer

logger = logging.getLogger(__name__)


def _detect_advertise_host(configured_host: str) -> str:
    if configured_host not in ("0.0.0.0", "::"):
        return configured_host
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def build_onvif_http_app(config: AppConfig, advertise_host: str) -> web.Application:
    app = web.Application()
    app.router.add_post(
        "/onvif/device_service", make_device_service_handler(config, advertise_host)
    )
    app.router.add_post(
        "/onvif/media_service", make_media_service_handler(config, advertise_host)
    )
    return app


async def run(config: AppConfig) -> None:
    advertise_host = _detect_advertise_host(config.server.host)
    logger.info("Advertising services at host %s", advertise_host)

    rtsp_server = OnvifSimRtspServer(config)
    rtsp_server.start()

    http_app = build_onvif_http_app(config, advertise_host)
    runner = web.AppRunner(http_app)
    await runner.setup()
    site = web.TCPSite(runner, config.server.host, config.server.http_port)
    await site.start()
    logger.info(
        "ONVIF SOAP server listening on http://%s:%d/onvif/{device,media}_service",
        config.server.host,
        config.server.http_port,
    )

    discovery_transport = await start_discovery_responder(
        advertise_host=advertise_host,
        http_port=config.server.http_port,
        device_name=config.server.device_name,
        device_uuid=str(uuid.uuid5(uuid.NAMESPACE_DNS, config.server.device_name)),
    )

    try:
        await asyncio.Event().wait()
    finally:
        discovery_transport.close()
        await runner.cleanup()
        rtsp_server.stop()


def main(config_path: str) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config(config_path)
    try:
        asyncio.run(run(config))
    except KeyboardInterrupt:
        logger.info("Shutting down")
