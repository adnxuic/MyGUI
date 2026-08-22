"""Parse bounded FullProf PRF refinement results into typed values.

This module deliberately has no Qt or Matplotlib dependencies.  It validates
one file completely before any Table or Figure state is allowed to change.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import re
from typing import Iterable

from mygui.resource_limits import ResourceLimits, load_resource_limits


_NUMBER_PATTERN = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?"
_NUMBER_RE = re.compile(_NUMBER_PATTERN)
_REFLECTION_RE = re.compile(
    rf"^\s*(?P<position>{_NUMBER_PATTERN}).*?"
    r"\(\s*(?P<h>[+-]?\d+)\s+(?P<k>[+-]?\d+)\s+"
    r"(?P<l>[+-]?\d+)\s*\)"
)
_PROFILE_HEADER = ("2theta", "yobs", "ycal", "yobs-ycal", "backg")


class FullProfPrfError(ValueError):
    """Report a PRF validation error with source-line context."""


@dataclass(frozen=True, slots=True)
class FullProfPrfMetadata:
    """Non-critical metadata recovered from a FullProf PRF preamble."""

    title: str
    chi2: float | None = None
    cell: tuple[float, float, float, float, float, float] | None = None
    space_group: str | None = None
    temperature: float | None = None
    wavelengths: tuple[float, ...] = ()


@dataclass(frozen=True, slots=True)
class FullProfProfileData:
    """Ordered profile columns and the recomputed residual."""

    two_theta: tuple[float, ...]
    yobs: tuple[float, ...]
    ycal: tuple[float, ...]
    prf_difference: tuple[float, ...]
    residual: tuple[float, ...]
    background: tuple[float, ...]

    def __post_init__(self) -> None:
        lengths = {
            len(self.two_theta),
            len(self.yobs),
            len(self.ycal),
            len(self.prf_difference),
            len(self.residual),
            len(self.background),
        }
        if lengths != {len(self.two_theta)}:
            raise ValueError("FullProf profile columns must have equal lengths.")
        if not self.two_theta:
            raise ValueError("FullProf profile must contain at least one point.")


@dataclass(frozen=True, slots=True)
class FullProfReflection:
    """One ordered reflection record with only confirmed v1 semantics."""

    position: float
    h: int
    k: int
    l: int  # noqa: E741 - crystallographic Miller index is conventionally l


@dataclass(frozen=True, slots=True)
class FullProfPrfResult:
    """Complete validated PRF result retained only for the current import."""

    source_name: str
    metadata: FullProfPrfMetadata
    profile: FullProfProfileData
    reflections: tuple[FullProfReflection, ...]


def _line_error(line_number: int, message: str, line: str = "") -> FullProfPrfError:
    context = line.strip().replace("\t", " ")
    if len(context) > 120:
        context = context[:117] + "..."
    suffix = f" Context: {context!r}." if context else ""
    return FullProfPrfError(f"PRF line {line_number}: {message}.{suffix}")


def _finite_number(token: str, line_number: int, label: str, line: str) -> float:
    try:
        value = float(str(token).replace("D", "E").replace("d", "e"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise _line_error(line_number, f"{label} must be numeric", line) from exc
    if not math.isfinite(value):
        raise _line_error(line_number, f"{label} must be finite", line)
    return value


def _optional_number(token: str | None) -> float | None:
    if token is None:
        return None
    try:
        value = float(token.replace("D", "E").replace("d", "e"))
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def _metadata(
    lines: list[str], header_index: int
) -> tuple[
    FullProfPrfMetadata,
    int | None,
    int | None,
]:
    preamble = [
        (index + 1, line) for index, line in enumerate(lines[:header_index]) if line.strip()
    ]
    first = preamble[0][1] if preamble else ""
    title = re.split(r"\bChi2\s*:", first, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    if not title:
        title = "FullProf refinement"

    chi_match = re.search(rf"\bChi2\s*:\s*({_NUMBER_PATTERN})", first, re.IGNORECASE)
    chi2 = _optional_number(chi_match.group(1) if chi_match else None)

    cell = None
    cell_match = re.search(
        r"\bCELL\s*:\s*(.*?)(?=\bSPGR\s*:|\bTEMP\s*:|$)",
        first,
        re.IGNORECASE,
    )
    if cell_match is not None:
        values = tuple(
            value
            for token in _NUMBER_RE.findall(cell_match.group(1))[:6]
            if (value := _optional_number(token)) is not None
        )
        if len(values) == 6:
            cell = values

    space_group = None
    space_match = re.search(
        r"\bSPGR\s*:\s*(.*?)(?=\bTEMP\s*:|$)",
        first,
        re.IGNORECASE,
    )
    if space_match is not None:
        candidate = space_match.group(1).strip()
        space_group = candidate or None

    temp_match = re.search(rf"\bTEMP\s*:\s*({_NUMBER_PATTERN})", first, re.IGNORECASE)
    temperature = _optional_number(temp_match.group(1) if temp_match else None)

    point_count = None
    reflection_count = None
    wavelengths: tuple[float, ...] = ()
    if len(preamble) >= 2:
        tokens = preamble[-2][1].split()
        if len(tokens) >= 2 and tokens[0].lstrip("+-").isdigit() and tokens[1].isdigit():
            point_count = int(tokens[1])
            candidates = tuple(_optional_number(token) for token in tokens[2:4])
            wavelengths = tuple(value for value in candidates if value is not None and value > 0.0)
    if preamble:
        tokens = preamble[-1][1].split()
        if tokens and tokens[0].isdigit():
            reflection_count = int(tokens[0])

    return (
        FullProfPrfMetadata(
            title=title,
            chi2=chi2,
            cell=cell,
            space_group=space_group,
            temperature=temperature,
            wavelengths=wavelengths,
        ),
        point_count,
        reflection_count,
    )


def _find_header(lines: Iterable[str]) -> int:
    for index, line in enumerate(lines):
        tokens = tuple(token.casefold() for token in re.split(r"\s+", line.strip()))
        if tokens[:5] == _PROFILE_HEADER:
            return index
    raise FullProfPrfError(
        "PRF profile header is missing; expected '2Theta Yobs Ycal Yobs-Ycal Backg'."
    )


def _parse_profile_line(line: str, line_number: int) -> tuple[float, ...]:
    tokens = line.split()
    if len(tokens) != 5:
        raise _line_error(
            line_number,
            "profile row must contain exactly five numeric columns",
            line,
        )
    return tuple(
        _finite_number(token, line_number, f"profile column {index}", line)
        for index, token in enumerate(tokens, start=1)
    )


def _parse_reflection(line: str, line_number: int) -> FullProfReflection:
    match = _REFLECTION_RE.search(line)
    if match is None:
        raise _line_error(
            line_number,
            "reflection row must contain a finite position and integer (h k l)",
            line,
        )
    position = _finite_number(
        match.group("position"),
        line_number,
        "reflection position",
        line,
    )
    try:
        h, k, ell = (int(match.group(key)) for key in ("h", "k", "l"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise _line_error(line_number, "reflection h/k/l must be integers", line) from exc
    return FullProfReflection(position, h, k, ell)


def parse_fullprof_prf_text(
    text: str,
    *,
    source_name: str = "FullProf",
    limits: ResourceLimits | None = None,
) -> FullProfPrfResult:
    """Parse already-decoded PRF text without mutating application state."""

    if not isinstance(text, str):
        raise TypeError("FullProf PRF input must be text.")
    limits = limits or load_resource_limits()
    if len(text.encode("utf-8")) > limits.max_prf_bytes:
        raise FullProfPrfError("FullProf PRF input exceeds the configured byte budget.")
    lines = text.splitlines()
    header_index = _find_header(lines)
    metadata, declared_points, declared_reflections = _metadata(lines, header_index)
    if declared_points is not None and declared_points > limits.max_prf_points:
        raise FullProfPrfError("FullProf PRF exceeds the configured profile-point budget.")
    if declared_reflections is not None and declared_reflections > limits.max_prf_reflections:
        raise FullProfPrfError("FullProf PRF exceeds the configured reflection budget.")

    profile_start = header_index + 1
    if declared_points is not None:
        if declared_points <= 0:
            raise FullProfPrfError("FullProf PRF profile contains no points.")
        profile_end = profile_start + declared_points
        if profile_end > len(lines):
            raise _line_error(
                len(lines) + 1,
                f"profile ended before declared point count {declared_points}",
            )
    else:
        profile_end = profile_start
        while profile_end < len(lines) and _REFLECTION_RE.search(lines[profile_end]) is None:
            profile_end += 1
        if profile_end == profile_start:
            raise FullProfPrfError("FullProf PRF profile contains no points.")
        if profile_end - profile_start > limits.max_prf_points:
            raise FullProfPrfError("FullProf PRF exceeds the configured profile-point budget.")

    columns = [
        _parse_profile_line(lines[index], index + 1) for index in range(profile_start, profile_end)
    ]
    if not columns:
        raise FullProfPrfError("FullProf PRF profile contains no points.")
    two_theta, yobs, ycal, prf_difference, background = (
        tuple(row[column] for row in columns) for column in range(5)
    )
    residual = tuple(observed - calculated for observed, calculated in zip(yobs, ycal))

    reflection_start = profile_end
    if declared_reflections is None:
        reflection_lines = list(range(reflection_start, len(lines)))
        if len(reflection_lines) > limits.max_prf_reflections:
            raise FullProfPrfError("FullProf PRF exceeds the configured reflection budget.")
    else:
        reflection_end = reflection_start + declared_reflections
        if reflection_end > len(lines):
            raise _line_error(
                len(lines) + 1,
                f"reflection section ended before declared count {declared_reflections}",
            )
        reflection_lines = list(range(reflection_start, reflection_end))
        for index in range(reflection_end, len(lines)):
            if lines[index].strip():
                raise _line_error(
                    index + 1, "unexpected content after reflection records", lines[index]
                )

    reflections = tuple(_parse_reflection(lines[index], index + 1) for index in reflection_lines)
    return FullProfPrfResult(
        source_name=str(source_name).strip() or "FullProf",
        metadata=metadata,
        profile=FullProfProfileData(
            two_theta=two_theta,
            yobs=yobs,
            ycal=ycal,
            prf_difference=prf_difference,
            residual=residual,
            background=background,
        ),
        reflections=reflections,
    )


def parse_fullprof_prf(
    file_name: str | Path,
    *,
    limits: ResourceLimits | None = None,
) -> FullProfPrfResult:
    """Validate and parse one bounded ``.prf`` file."""

    path = Path(file_name)
    if path.suffix.casefold() != ".prf":
        raise FullProfPrfError("Only FullProf .prf files are supported.")
    if not path.is_file():
        raise FullProfPrfError(f"FullProf PRF file does not exist: {path}")
    limits = limits or load_resource_limits()
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise FullProfPrfError(f"Could not inspect FullProf PRF file: {path}") from exc
    if size > limits.max_prf_bytes:
        raise FullProfPrfError("FullProf PRF input exceeds the configured byte budget.")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise FullProfPrfError(f"Could not read FullProf PRF file: {path}") from exc
    if len(payload) > limits.max_prf_bytes:
        raise FullProfPrfError("FullProf PRF input exceeds the configured byte budget.")
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FullProfPrfError("FullProf PRF file must be UTF-8 or ASCII text.") from exc
    return parse_fullprof_prf_text(text, source_name=path.stem, limits=limits)


__all__ = [
    "FullProfPrfError",
    "FullProfPrfMetadata",
    "FullProfProfileData",
    "FullProfReflection",
    "FullProfPrfResult",
    "parse_fullprof_prf",
    "parse_fullprof_prf_text",
]
