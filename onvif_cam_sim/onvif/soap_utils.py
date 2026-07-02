"""Shared SOAP parsing/rendering helpers for the device and media services."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from aiohttp import web
from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = Path(__file__).parent / "templates"

jinja_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["xml"]),
)

SOAP_NS = "{http://www.w3.org/2003/05/soap-envelope}"


def local_name(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def parse_soap_body(body: bytes) -> ET.Element | None:
    """Return the SOAP Body's single child element (the request op), or None."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None
    soap_body = root.find(f"{SOAP_NS}Body")
    if soap_body is None or len(soap_body) == 0:
        return None
    return soap_body[0]


def find_text_anywhere(element: ET.Element, tag_local_name: str) -> str | None:
    for child in element.iter():
        if local_name(child.tag) == tag_local_name:
            return child.text
    return None


def soap_response(xml: str) -> web.Response:
    return web.Response(text=xml, content_type="application/soap+xml")


def soap_fault(reason: str) -> web.Response:
    xml = jinja_env.get_template("fault.xml").render(reason=reason)
    return web.Response(text=xml, content_type="application/soap+xml", status=500)
