"""ONVIF Device Management service (minimal subset)."""

from __future__ import annotations

import datetime
import logging
from typing import Callable, Coroutine

from aiohttp import web

from onvif_cam_sim.config import AppConfig
from onvif_cam_sim.onvif.soap_utils import (
    jinja_env,
    local_name,
    parse_soap_body,
    soap_fault,
    soap_response,
)

logger = logging.getLogger(__name__)

Handler = Callable[[web.Request], Coroutine[None, None, web.Response]]


def make_device_service_handler(config: AppConfig, advertise_host: str) -> Handler:
    async def handler(request: web.Request) -> web.Response:
        body = await request.read()
        op = parse_soap_body(body)
        action = local_name(op.tag) if op is not None else None
        logger.info("device_service: %s", action)

        if action == "GetDeviceInformation":
            xml = jinja_env.get_template("device_information.xml").render(
                manufacturer=config.server.manufacturer,
                model="onvif-cam-sim",
                firmware_version="1.0.0",
                serial_number="SIM0001",
                hardware_id="SIM-HW-1",
            )
        elif action == "GetCapabilities":
            xml = jinja_env.get_template("capabilities.xml").render(
                host=advertise_host,
                http_port=config.server.http_port,
            )
        elif action == "GetServices":
            xml = jinja_env.get_template("services.xml").render(
                host=advertise_host,
                http_port=config.server.http_port,
            )
        elif action == "GetSystemDateAndTime":
            now = datetime.datetime.now(datetime.timezone.utc)
            xml = jinja_env.get_template("system_date_and_time.xml").render(now=now)
        else:
            return soap_fault(f"Unsupported action: {action}")

        return soap_response(xml)

    return handler
