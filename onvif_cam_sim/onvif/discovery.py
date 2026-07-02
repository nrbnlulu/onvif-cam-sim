"""Minimal WS-Discovery responder: replies to multicast Probe with a ProbeMatch."""

from __future__ import annotations

import asyncio
import logging
import re
import socket
import struct
import uuid

logger = logging.getLogger(__name__)

MCAST_GROUP = "239.255.255.250"
MCAST_PORT = 3702

_PROBE_RE = re.compile(rb"<[a-zA-Z0-9]*:?Probe[ >/]")
_MESSAGE_ID_RE = re.compile(rb"<[a-zA-Z0-9]*:?MessageID>([^<]+)</[a-zA-Z0-9]*:?MessageID>")

_PROBE_MATCH_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
    xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
    xmlns:wsd="http://schemas.xmlsoap.org/ws/2005/04/discovery"
    xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <soap:Header>
    <wsa:MessageID>urn:uuid:{message_id}</wsa:MessageID>
    <wsa:RelatesTo>{relates_to}</wsa:RelatesTo>
    <wsa:To>http://www.w3.org/2005/08/addressing/anonymous</wsa:To>
    <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/ProbeMatches</wsa:Action>
  </soap:Header>
  <soap:Body>
    <wsd:ProbeMatches>
      <wsd:ProbeMatch>
        <wsa:EndpointReference>
          <wsa:Address>urn:uuid:{device_uuid}</wsa:Address>
        </wsa:EndpointReference>
        <wsd:Types>dn:NetworkVideoTransmitter</wsd:Types>
        <wsd:Scopes>onvif://www.onvif.org/type/video_encoder onvif://www.onvif.org/name/{device_name}</wsd:Scopes>
        <wsd:XAddrs>{xaddr}</wsd:XAddrs>
        <wsd:MetadataVersion>1</wsd:MetadataVersion>
      </wsd:ProbeMatch>
    </wsd:ProbeMatches>
  </soap:Body>
</soap:Envelope>"""


class WSDiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(self, device_uuid: str, device_name: str, xaddr: str):
        self._device_uuid = device_uuid
        self._device_name = device_name
        self._xaddr = xaddr
        self._transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self._transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if not _PROBE_RE.search(data):
            return
        match = _MESSAGE_ID_RE.search(data)
        relates_to = match.group(1).decode() if match else ""
        response = _PROBE_MATCH_TEMPLATE.format(
            message_id=uuid.uuid4(),
            relates_to=relates_to,
            device_uuid=self._device_uuid,
            device_name=self._device_name,
            xaddr=self._xaddr,
        ).encode()
        logger.info("WS-Discovery: replying to Probe from %s", addr)
        assert self._transport is not None
        self._transport.sendto(response, addr)


async def start_discovery_responder(
    advertise_host: str, http_port: int, device_name: str, device_uuid: str
) -> asyncio.DatagramTransport:
    xaddr = f"http://{advertise_host}:{http_port}/onvif/device_service"

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    sock.bind(("", MCAST_PORT))
    mreq = struct.pack("4sl", socket.inet_aton(MCAST_GROUP), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    sock.setblocking(False)

    loop = asyncio.get_running_loop()
    transport, _protocol = await loop.create_datagram_endpoint(
        lambda: WSDiscoveryProtocol(device_uuid, device_name, xaddr),
        sock=sock,
    )
    logger.info(
        "WS-Discovery responder listening on %s:%d (xaddr=%s)",
        MCAST_GROUP,
        MCAST_PORT,
        xaddr,
    )
    return transport
