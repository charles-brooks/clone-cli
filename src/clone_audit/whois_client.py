"""WHOIS lookup helpers."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

import requests

from .models import WhoisRecord

try:  # pragma: no cover - optional dependency
    import whois  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    whois = None  # type: ignore

_RDAP_TIMEOUT = 10.0
_RDAP_HEADERS = {
    "User-Agent": "clone-audit-whois/1.0",
    "Accept": "application/rdap+json",
}


class WhoisClient:
    def lookup(self, target: str) -> WhoisRecord:
        domain = self._extract_domain(target)
        if not domain:
            return WhoisRecord(
                domain=target,
                registrar=None,
                creation_date=None,
                updated_date=None,
                expiration_date=None,
                raw_text=None,
                error="Unable to determine domain",
            )
        if whois is None:
            fallback = self._lookup_rdap(domain)
            if fallback is not None:
                return fallback
            return WhoisRecord(
                domain=domain,
                registrar=None,
                creation_date=None,
                updated_date=None,
                expiration_date=None,
                raw_text=None,
                error="python-whois not installed",
            )
        try:
            record = whois.whois(domain)
        except Exception as exc:  # pragma: no cover - network edge
            fallback = self._lookup_rdap(domain)
            if fallback is not None:
                return fallback
            return WhoisRecord(
                domain=domain,
                registrar=None,
                creation_date=None,
                updated_date=None,
                expiration_date=None,
                raw_text=None,
                error=str(exc),
            )
        registrar = self._get_field(record, "registrar")
        creation_date = self._coerce_datetime(self._first(self._get_field(record, "creation_date")))
        updated_date = self._coerce_datetime(self._first(self._get_field(record, "updated_date")))
        expiration_date = self._coerce_datetime(self._first(self._get_field(record, "expiration_date")))
        name_servers = self._normalize_nameservers(record)
        raw_text = record.text if hasattr(record, "text") else None
        if raw_text is None and isinstance(record, dict):
            raw_text = record.get("raw") or record.get("rawtext")
        return WhoisRecord(
            domain=domain,
            registrar=registrar,
            creation_date=creation_date,
            updated_date=updated_date,
            expiration_date=expiration_date,
            name_servers=name_servers,
            raw_text=raw_text,
            error=None,
        )

    def _lookup_rdap(self, domain: str) -> Optional[WhoisRecord]:
        rdap_url = f"https://rdap.org/domain/{domain}"
        try:
            response = requests.get(rdap_url, timeout=_RDAP_TIMEOUT, headers=_RDAP_HEADERS)
            response.raise_for_status()
        except requests.RequestException:
            return None

        try:
            data = response.json()
        except json.JSONDecodeError:
            return None

        registrar = self._extract_rdap_registrar(data)
        creation_date = self._extract_rdap_event(data, "registration")
        updated_date = self._extract_rdap_event(data, "last changed")
        expiration_date = self._extract_rdap_event(data, "expiration")
        name_servers = self._extract_rdap_nameservers(data)
        raw_text = json.dumps(data, indent=2)

        return WhoisRecord(
            domain=domain,
            registrar=registrar,
            creation_date=creation_date,
            updated_date=updated_date,
            expiration_date=expiration_date,
            name_servers=name_servers,
            raw_text=raw_text,
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
    def _first(value: Any) -> Any:
        if isinstance(value, (list, tuple)) and value:
            return value[0]
        return value

    @staticmethod
    def _get_field(record: Any, name: str) -> Any:
        if record is None:
            return None
        if isinstance(record, dict):
            return record.get(name)
        return getattr(record, name, None)

    @staticmethod
    def _coerce_datetime(value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            # Try parsing ISO-style timestamps before falling back
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                pass
            for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y.%m.%d %H:%M:%S"):
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
        return None

    @staticmethod
    def _normalize_nameservers(record: Any) -> tuple[str, ...]:
        if isinstance(record, dict):
            raw = record.get("name_servers")
        else:
            raw = getattr(record, "name_servers", None)
        if raw is None:
            return tuple()
        if isinstance(raw, str):
            items = [raw]
        else:
            items = list(raw)
        normalized = sorted({item.strip().lower() for item in items if item})
        return tuple(normalized)

    @staticmethod
    def _extract_rdap_registrar(data: dict[str, Any]) -> Optional[str]:
        entities = data.get("entities")
        if isinstance(entities, list):
            for entity in entities:
                roles = entity.get("roles") if isinstance(entity, dict) else None
                if roles and any(role.lower() == "registrar" for role in roles if isinstance(role, str)):
                    name = WhoisClient._extract_vcard_fn(entity)
                    if name:
                        return name
        registrar_name = data.get("registrarName")
        if isinstance(registrar_name, str):
            return registrar_name
        return None

    @staticmethod
    def _extract_vcard_fn(entity: Any) -> Optional[str]:
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

    @staticmethod
    def _extract_rdap_event(data: dict[str, Any], action: str) -> Optional[datetime]:
        events = data.get("events")
        if not isinstance(events, list):
            return None
        for event in events:
            if (
                isinstance(event, dict)
                and event.get("eventAction") == action
                and isinstance(event.get("eventDate"), str)
            ):
                return WhoisClient._coerce_datetime(event["eventDate"])
        return None

    @staticmethod
    def _extract_rdap_nameservers(data: dict[str, Any]) -> tuple[str, ...]:
        servers = data.get("nameservers")
        if not isinstance(servers, list):
            return tuple()
        collected = []
        for server in servers:
            if isinstance(server, dict):
                ldh = server.get("ldhName")
                if isinstance(ldh, str):
                    collected.append(ldh.lower())
        return tuple(sorted(set(collected)))


__all__ = ["WhoisClient"]
