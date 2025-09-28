"""Hosting provider lookup helpers."""
from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlparse

import requests

from .models import HostingRecord

_USER_AGENT = "clone-audit-hosting/1.0"
_RDAP_TIMEOUT = 10.0


@dataclass(slots=True)
class _ParsedEntity:
    name: Optional[str]
    roles: tuple[str, ...]


class HostingClient:
    """Resolve hosting provider details via RDAP."""

    def lookup(self, target: str) -> HostingRecord:
        domain = self._extract_domain(target)
        if not domain:
            return HostingRecord(
                domain=target,
                ip=None,
                network_name=None,
                organization=None,
                country=None,
                source=None,
                raw=None,
                error="Unable to determine domain",
            )

        try:
            ip_address = self._resolve_ip(domain)
        except socket.gaierror as exc:
            return HostingRecord(
                domain=domain,
                ip=None,
                network_name=None,
                organization=None,
                country=None,
                source=None,
                raw=None,
                error=str(exc),
            )

        rdap_data, rdap_url = self._fetch_rdap(ip_address)
        if rdap_data is None:
            return HostingRecord(
                domain=domain,
                ip=ip_address,
                network_name=None,
                organization=None,
                country=None,
                source=rdap_url,
                raw=None,
                error="RDAP lookup failed",
            )

        network_name = rdap_data.get("name")
        country = rdap_data.get("country")
        organization = self._select_entity_name(rdap_data)
        raw_data = rdap_data if isinstance(rdap_data, dict) else None

        return HostingRecord(
            domain=domain,
            ip=ip_address,
            network_name=network_name,
            organization=organization,
            country=country,
            source=rdap_url,
            raw=raw_data,
            error=None,
        )

    @staticmethod
    def _extract_domain(target: str) -> str:
        parsed = urlparse(target)
        if parsed.scheme and parsed.netloc:
            return parsed.netloc.split(":")[0]
        if "." in target:
            return target
        return ""

    @staticmethod
    def _resolve_ip(domain: str) -> str:
        infos = socket.getaddrinfo(domain, None)
        # Prefer IPv4 addresses for readability
        for family, _, _, _, sockaddr in infos:
            if family == socket.AF_INET:
                return sockaddr[0]
        # Fallback to the first result if IPv4 not available
        return infos[0][4][0]

    def _fetch_rdap(self, ip: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        rdap_url = f"https://rdap.org/ip/{ip}"
        try:
            response = requests.get(
                rdap_url,
                timeout=_RDAP_TIMEOUT,
                headers={"User-Agent": _USER_AGENT, "Accept": "application/rdap+json"},
            )
            response.raise_for_status()
        except requests.RequestException:
            return None, rdap_url

        try:
            data = response.json()
        except json.JSONDecodeError:
            return None, rdap_url

        return data, response.url or rdap_url

    def _select_entity_name(self, rdap_data: dict[str, Any]) -> Optional[str]:
        entities = rdap_data.get("entities")
        if not isinstance(entities, list):
            return None

        parsed_entities = []
        for entity in entities:
            name = self._extract_vcard_name(entity)
            roles = tuple(role.lower() for role in entity.get("roles", []) if isinstance(role, str))
            parsed_entities.append(_ParsedEntity(name=name, roles=roles))

        # Prefer registrant / organisation style roles
        preferred_roles = (
            "registrant",
            "administrative",
            "technical",
            "abuse",
            "billing",
        )
        for role in preferred_roles:
            for entity in parsed_entities:
                if entity.name and role in entity.roles:
                    return entity.name

        # Fallback to any named entity
        for entity in parsed_entities:
            if entity.name:
                return entity.name
        return None

    @staticmethod
    def _extract_vcard_name(entity: Any) -> Optional[str]:
        vcard = entity.get("vcardArray") if isinstance(entity, dict) else None
        if not (isinstance(vcard, list) and len(vcard) == 2 and isinstance(vcard[1], list)):
            return None
        for item in vcard[1]:
            if (
                isinstance(item, list)
                and len(item) == 4
                and item[0] == "fn"
                and isinstance(item[3], str)
            ):
                return item[3]
        return None


__all__ = ["HostingClient"]
