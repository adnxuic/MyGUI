"""Canonical JSON envelopes and SHA-256 integrity for dual-slot documents."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from mygui.application_settings.storage.keys import (
    CURRENT_SCHEMA_VERSION,
    MAX_ENVELOPE_BYTES,
    MAX_REVISION,
    MIN_REVISION,
    SCHEMA_APPLICATION_SETTINGS,
    SCHEMA_COLOR_LIBRARY_SETTINGS,
)


class EnvelopeError(ValueError):
    """Raised when an envelope cannot be encoded or decoded."""


def _reject_nonfinite(value: str) -> None:
    raise EnvelopeError(f"non-finite JSON value is not allowed: {value}")


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EnvelopeError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def canonical_json_bytes(value: Any) -> bytes:
    """Return UTF-8 JSON with sorted keys, compact separators, and no NaN."""

    try:
        text = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise EnvelopeError("value is not canonical JSON") from exc
    return text.encode("utf-8")


def envelope_sha256(envelope: Mapping[str, Any]) -> str:
    """Return the hex digest of an envelope with the sha256 field excluded."""

    body = {key: envelope[key] for key in envelope if key != "sha256"}
    return hashlib.sha256(canonical_json_bytes(body)).hexdigest()


def _require_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EnvelopeError(f"{label} must be an integer")
    return value


def _loads_strict(text: str) -> Any:
    try:
        return json.loads(
            text,
            parse_constant=_reject_nonfinite,
            object_pairs_hook=_object_pairs,
        )
    except EnvelopeError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise EnvelopeError("envelope is not valid JSON") from exc


@dataclass(frozen=True, slots=True)
class DecodedEnvelope:
    """Structurally valid envelope after hash and size checks."""

    schema: str
    schema_version: int
    revision: int
    payload: dict[str, Any]
    sha256: str
    encoded: str

    @property
    def is_future(self) -> bool:
        """Return whether the envelope uses a newer schema version."""

        return self.schema_version > CURRENT_SCHEMA_VERSION

    @property
    def encoded_bytes(self) -> bytes:
        """Return the stored UTF-8 envelope bytes."""

        return self.encoded.encode("utf-8")


class EnvelopeCodec:
    """Encode and decode dual-slot document envelopes."""

    current_schema_version = CURRENT_SCHEMA_VERSION
    application_schema = SCHEMA_APPLICATION_SETTINGS
    color_library_schema = SCHEMA_COLOR_LIBRARY_SETTINGS
    max_envelope_bytes = MAX_ENVELOPE_BYTES
    min_revision = MIN_REVISION
    max_revision = MAX_REVISION

    def encode(
        self,
        *,
        schema: str,
        payload: Mapping[str, Any],
        revision: int,
        schema_version: int = CURRENT_SCHEMA_VERSION,
    ) -> str:
        """Return a complete canonical envelope JSON string."""

        if not isinstance(schema, str) or not schema:
            raise EnvelopeError("schema must be a non-empty string")
        schema_version = _require_int(schema_version, "schema_version")
        if schema_version < 1:
            raise EnvelopeError("schema_version must be >= 1")
        revision = _require_int(revision, "revision")
        if revision < MIN_REVISION or revision > MAX_REVISION:
            raise EnvelopeError(
                f"revision must be in {MIN_REVISION}..{MAX_REVISION}"
            )
        if not isinstance(payload, Mapping) or isinstance(payload, (str, bytes)):
            raise EnvelopeError("payload must be a JSON object")
        try:
            payload_copy = _loads_strict(
                json.dumps(dict(payload), allow_nan=False)
            )
        except (TypeError, ValueError) as exc:
            raise EnvelopeError("payload is not JSON-serializable") from exc
        if not isinstance(payload_copy, dict):
            raise EnvelopeError("payload must be a JSON object")
        body = {
            "payload": payload_copy,
            "revision": revision,
            "schema": schema,
            "schema_version": schema_version,
        }
        encoded = canonical_json_bytes({**body, "sha256": envelope_sha256(body)})
        if len(encoded) > MAX_ENVELOPE_BYTES:
            raise EnvelopeError("envelope exceeds 1 MiB")
        return encoded.decode("utf-8")

    def decode(
        self,
        raw: object,
        *,
        expected_schema: str,
    ) -> DecodedEnvelope:
        """Decode, size-check, and hash-verify one stored envelope."""

        text = _raw_text(raw)
        encoded_bytes = text.encode("utf-8")
        if len(encoded_bytes) > MAX_ENVELOPE_BYTES:
            raise EnvelopeError("envelope exceeds 1 MiB")
        data = _loads_strict(text)
        if not isinstance(data, dict):
            raise EnvelopeError("envelope must be a JSON object")
        schema = data.get("schema")
        if schema != expected_schema:
            raise EnvelopeError("envelope schema does not match this document")
        schema_version = _require_int(data.get("schema_version"), "schema_version")
        if schema_version < 1:
            raise EnvelopeError("schema_version must be >= 1")
        revision = _require_int(data.get("revision"), "revision")
        if revision < MIN_REVISION or revision > MAX_REVISION:
            raise EnvelopeError(
                f"revision must be in {MIN_REVISION}..{MAX_REVISION}"
            )
        payload = data.get("payload")
        if not isinstance(payload, dict):
            raise EnvelopeError("payload must be a JSON object")
        digest = data.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise EnvelopeError("sha256 must be a 64-character hex digest")
        try:
            int(digest, 16)
        except ValueError as exc:
            raise EnvelopeError("sha256 must be a 64-character hex digest") from exc
        required = {"schema", "schema_version", "revision", "payload", "sha256"}
        extra = set(data) - required
        if schema_version == CURRENT_SCHEMA_VERSION and extra:
            raise EnvelopeError("current schema envelope has unknown fields")
        expected = envelope_sha256(data)
        if digest.lower() != expected:
            raise EnvelopeError("envelope sha256 mismatch")
        return DecodedEnvelope(
            schema=schema,
            schema_version=schema_version,
            revision=revision,
            payload=payload,
            sha256=expected,
            encoded=text,
        )


def _raw_text(raw: object) -> str:
    if raw is None:
        raise EnvelopeError("envelope is empty")
    if isinstance(raw, bytes):
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EnvelopeError("envelope is not UTF-8") from exc
    if isinstance(raw, bytearray):
        return _raw_text(bytes(raw))
    if isinstance(raw, str):
        if not raw:
            raise EnvelopeError("envelope is empty")
        return raw
    try:
        as_bytes = bytes(raw)
    except (TypeError, ValueError) as exc:
        text = str(raw)
        if not text:
            raise EnvelopeError("envelope is empty") from exc
        return text
    if as_bytes:
        try:
            return as_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EnvelopeError("envelope is not UTF-8") from exc
    text = str(raw)
    if not text:
        raise EnvelopeError("envelope is empty")
    return text
