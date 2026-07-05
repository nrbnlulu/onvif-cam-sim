"""Background generator that synthesizes motion-detection events per stream."""

from __future__ import annotations

import asyncio
import logging
import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable

from onvif_cam_sim.config import AppConfig

logger = logging.getLogger(__name__)

# (topic, Data SimpleItem field name) per object class.
_TOPIC_BY_CLASS: dict[str, tuple[str, str]] = {
    "human": ("tns1:RuleEngine/HumanDetector/Human", "IsHuman"),
    "vehicle": ("tns1:RuleEngine/VehicleDetector/Vehicle", "IsVehicle"),
    "animal": ("tns1:RuleEngine/AnimalDetector/Animal", "IsAnimal"),
    "motion": ("tns1:RuleEngine/MotionDetector/Motion", "IsMotion"),
}


@dataclass(slots=True, kw_only=True)
class MotionNotification:
    topic: str
    field_name: str
    state: bool
    utc_time: str
    source_token: str
    object_id: str


class MotionEventGenerator:
    """Periodically picks a random stream + object class and fires a start/stop detection."""

    def __init__(self, config: AppConfig, broadcast: Callable[[MotionNotification], Awaitable[None]]):
        self._streams = config.streams
        self._events = config.events
        self._broadcast = broadcast
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._events.enabled and self._streams:
            self._task = asyncio.create_task(self._run())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(random.uniform(self._events.min_interval_s, self._events.max_interval_s))
            stream = random.choice(self._streams)
            object_class = random.choice(self._events.classes)
            topic, field_name = _TOPIC_BY_CLASS[object_class]
            source_token = f"vs{stream.index}"
            object_id = uuid.uuid4().hex[:8]

            await self._emit(topic, field_name, True, source_token, object_id)
            active_duration = random.uniform(
                self._events.active_duration_min_s, self._events.active_duration_max_s
            )
            await asyncio.sleep(active_duration)
            await self._emit(topic, field_name, False, source_token, object_id)

    async def _emit(
        self, topic: str, field_name: str, state: bool, source_token: str, object_id: str
    ) -> None:
        notification = MotionNotification(
            topic=topic,
            field_name=field_name,
            state=state,
            utc_time=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            source_token=source_token,
            object_id=object_id,
        )
        logger.info("Motion event: topic=%s state=%s source=%s", topic, state, source_token)
        await self._broadcast(notification)
