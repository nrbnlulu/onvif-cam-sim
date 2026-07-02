"""ONVIF Media service (minimal subset)."""

from __future__ import annotations

import logging
from typing import Callable, Coroutine

from aiohttp import web

from onvif_cam_sim.config import AppConfig
from onvif_cam_sim.onvif.soap_utils import (
    find_text_anywhere,
    jinja_env,
    local_name,
    parse_soap_body,
    soap_fault,
    soap_response,
)

logger = logging.getLogger(__name__)

Handler = Callable[[web.Request], Coroutine[None, None, web.Response]]


def make_media_service_handler(config: AppConfig, advertise_host: str) -> Handler:
    streams_by_profile = {f"profile{s.index}": s for s in config.streams}

    async def handler(request: web.Request) -> web.Response:
        body = await request.read()
        op = parse_soap_body(body)
        action = local_name(op.tag) if op is not None else None
        logger.info("media_service: %s", action)

        if action == "GetProfiles":
            xml = jinja_env.get_template("profiles.xml").render(streams=config.streams)
        elif action == "GetVideoSources":
            xml = jinja_env.get_template("video_sources.xml").render(streams=config.streams)
        elif action == "GetStreamUri":
            profile_token = find_text_anywhere(op, "ProfileToken")
            stream = streams_by_profile.get(profile_token or "")
            if stream is None:
                return soap_fault(f"Unknown ProfileToken: {profile_token}")
            uri = f"rtsp://{advertise_host}:{config.server.rtsp_port}{stream.mount_path}"
            xml = jinja_env.get_template("stream_uri.xml").render(uri=uri)
        else:
            return soap_fault(f"Unsupported action: {action}")

        return soap_response(xml)

    return handler
