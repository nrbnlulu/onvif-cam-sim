"""ONVIF Events service: WS-BaseNotification PullPoint subscriptions (minimal subset)."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Coroutine

from aiohttp import web

from onvif_cam_sim.onvif.motion_events import MotionNotification
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

_SUBSCRIPTION_LIFETIME = timedelta(minutes=2)
_DEFAULT_PULL_TIMEOUT_S = 10.0
_MAX_PULL_TIMEOUT_S = 30.0

_DURATION_RE = re.compile(
    r"^-?P(?:(?P<days>\d+)D)?"
    r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>[\d.]+)S)?)?$"
)


def _parse_iso8601_duration(text: str | None) -> float | None:
    if not text:
        return None
    match = _DURATION_RE.match(text)
    if not match:
        return None
    parts = match.groupdict()
    return (
        float(parts["days"] or 0) * 86400
        + float(parts["hours"] or 0) * 3600
        + float(parts["minutes"] or 0) * 60
        + float(parts["seconds"] or 0)
    )


def _fmt_time(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(slots=True, kw_only=True)
class PullPointSubscription:
    id: str
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    expires: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + _SUBSCRIPTION_LIFETIME
    )


class EventService:
    """Holds active PullPoint subscriptions and fans out motion notifications to them."""

    def __init__(self) -> None:
        self._subscriptions: dict[str, PullPointSubscription] = {}

    def create_subscription(self) -> PullPointSubscription:
        sub = PullPointSubscription(id=uuid.uuid4().hex)
        self._subscriptions[sub.id] = sub
        return sub

    def get(self, sub_id: str) -> PullPointSubscription | None:
        self._evict_expired()
        return self._subscriptions.get(sub_id)

    def remove(self, sub_id: str) -> None:
        self._subscriptions.pop(sub_id, None)

    def renew(self, sub: PullPointSubscription) -> None:
        sub.expires = datetime.now(timezone.utc) + _SUBSCRIPTION_LIFETIME

    async def broadcast(self, notification: MotionNotification) -> None:
        self._evict_expired()
        for sub in self._subscriptions.values():
            await sub.queue.put(notification)

    def _evict_expired(self) -> None:
        now = datetime.now(timezone.utc)
        expired = [sid for sid, sub in self._subscriptions.items() if sub.expires < now]
        for sid in expired:
            del self._subscriptions[sid]


async def _drain_queue(
    queue: asyncio.Queue, timeout_s: float, limit: int
) -> list[MotionNotification]:
    messages: list[MotionNotification] = []
    try:
        messages.append(await asyncio.wait_for(queue.get(), timeout=timeout_s))
    except TimeoutError:
        return messages
    while len(messages) < limit:
        try:
            messages.append(queue.get_nowait())
        except asyncio.QueueEmpty:
            break
    return messages


def make_event_service_handler(advertise_host: str, http_port: int, events: EventService) -> Handler:
    async def handler(request: web.Request) -> web.Response:
        body = await request.read()
        op = parse_soap_body(body)
        action = local_name(op.tag) if op is not None else None
        logger.info("event_service: %s", action)

        if action != "CreatePullPointSubscription":
            return soap_fault(f"Unsupported action: {action}")

        sub = events.create_subscription()
        address = f"http://{advertise_host}:{http_port}/onvif/events/pullpoint/{sub.id}"
        now = datetime.now(timezone.utc)
        xml = jinja_env.get_template("create_pullpoint_subscription.xml").render(
            address=address,
            current_time=_fmt_time(now),
            termination_time=_fmt_time(sub.expires),
        )
        return soap_response(xml)

    return handler


def make_pullpoint_handler(events: EventService) -> Handler:
    async def handler(request: web.Request) -> web.Response:
        sub_id = request.match_info["sub_id"]
        sub = events.get(sub_id)
        if sub is None:
            return soap_fault(f"Unknown or expired subscription: {sub_id}")

        body = await request.read()
        op = parse_soap_body(body)
        action = local_name(op.tag) if op is not None else None
        logger.info("pullpoint[%s]: %s", sub_id, action)

        if action == "PullMessages":
            timeout_s = _parse_iso8601_duration(find_text_anywhere(op, "Timeout"))
            timeout_s = min(timeout_s or _DEFAULT_PULL_TIMEOUT_S, _MAX_PULL_TIMEOUT_S)
            limit = int(find_text_anywhere(op, "MessageLimit") or 50)
            messages = await _drain_queue(sub.queue, timeout_s, limit)
            now = datetime.now(timezone.utc)
            xml = jinja_env.get_template("pull_messages_response.xml").render(
                current_time=_fmt_time(now),
                termination_time=_fmt_time(sub.expires),
                messages=messages,
            )
            return soap_response(xml)

        if action == "Renew":
            events.renew(sub)
            now = datetime.now(timezone.utc)
            xml = jinja_env.get_template("renew_response.xml").render(
                current_time=_fmt_time(now),
                termination_time=_fmt_time(sub.expires),
            )
            return soap_response(xml)

        if action == "Unsubscribe":
            events.remove(sub_id)
            xml = jinja_env.get_template("unsubscribe_response.xml").render()
            return soap_response(xml)

        return soap_fault(f"Unsupported action: {action}")

    return handler
