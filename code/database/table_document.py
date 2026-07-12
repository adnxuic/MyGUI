from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Iterable, Sequence
from uuid import uuid4

import numpy as np
import pandas as pd


DEFAULT_ROWS = 20
DEFAULT_COLUMNS = 5
DEFAULT_COLUMN_WIDTH = 96
INVALID_NAME_CHARS = {"/", "\\"}


def validate_component_name(name: str, label: str = "Name") -> str:
    cleaned = str(name).strip()
    if not cleaned:
        raise ValueError(f"{label} must not be empty.")
    if any(character in cleaned for character in INVALID_NAME_CHARS):
        raise ValueError(f"{label} must not contain / or \\.")
    return cleaned


class ColumnType(str, Enum):
    AUTO = "auto"
    NUMBER = "number"
    TEXT = "text"
    DATETIME = "datetime"
    BOOLEAN = "boolean"


PANDAS_DTYPES: dict[ColumnType, str] = {
    ColumnType.NUMBER: "Float64",
    ColumnType.TEXT: "string",
    ColumnType.DATETIME: "datetime64[ns]",
    ColumnType.BOOLEAN: "boolean",
}


def new_id() -> str:
    return str(uuid4())


def is_missing(value: Any) -> bool:
    if value is None or value is pd.NA or value is pd.NaT:
        return True
    if isinstance(value, str):
        return value == ""
    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return bool(result) if isinstance(result, (bool, np.bool_)) else False


def _is_boolean_like(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return True
    if isinstance(value, str):
        return value.strip().casefold() in {"true", "false", "yes", "no"}
    return False


def _is_number_like(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return False
    try:
        float(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return True


def _is_datetime_like(value: Any) -> bool:
    if isinstance(value, (datetime, date, pd.Timestamp, np.datetime64)):
        return True
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text or not any(separator in text for separator in ("-", "/", ":", "T")):
        return False
    try:
        parsed = pd.to_datetime(text, errors="raise")
    except (TypeError, ValueError, OverflowError):
        return False
    return not pd.isna(parsed)


def infer_column_type(values: Iterable[Any]) -> ColumnType:
    present = [value for value in values if not is_missing(value)]
    if not present:
        return ColumnType.AUTO
    if all(_is_boolean_like(value) for value in present):
        return ColumnType.BOOLEAN
    if all(_is_number_like(value) for value in present):
        return ColumnType.NUMBER
    if all(_is_datetime_like(value) for value in present):
        return ColumnType.DATETIME
    return ColumnType.TEXT


def coerce_value(value: Any, column_type: ColumnType) -> Any:
    if is_missing(value):
        return pd.NaT if column_type == ColumnType.DATETIME else pd.NA
    if column_type == ColumnType.AUTO:
        raise ValueError("An automatic column must be resolved before accepting data.")
    if column_type == ColumnType.TEXT:
        return str(value)
    if column_type == ColumnType.NUMBER:
        if isinstance(value, (bool, np.bool_)):
            raise ValueError(f"{value!r} is not a number.")
        try:
            return float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{value!r} is not a valid number.") from exc
    if column_type == ColumnType.BOOLEAN:
        if isinstance(value, (bool, np.bool_)):
            return bool(value)
        if isinstance(value, (int, np.integer)) and value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().casefold()
            if normalized in {"true", "yes", "1"}:
                return True
            if normalized in {"false", "no", "0"}:
                return False
        raise ValueError(f"{value!r} is not a valid boolean.")
    if column_type == ColumnType.DATETIME:
        try:
            result = pd.Timestamp(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"{value!r} is not a valid date/time.") from exc
        if result.tzinfo is not None:
            result = result.tz_localize(None)
        return result
    raise ValueError(f"Unsupported column type: {column_type}")


def coerce_series(values: Sequence[Any] | pd.Series, column_type: ColumnType) -> pd.Series:
    raw = list(values)
    resolved = infer_column_type(raw) if column_type == ColumnType.AUTO else column_type
    if resolved == ColumnType.AUTO:
        return pd.Series([pd.NA] * len(raw), dtype="object")
    converted = [coerce_value(value, resolved) for value in raw]
    return pd.Series(converted, dtype=PANDAS_DTYPES[resolved])


def display_value(value: Any, column_type: ColumnType) -> str:
    if is_missing(value):
        return ""
    if column_type == ColumnType.BOOLEAN:
        return "true" if bool(value) else "false"
    if column_type == ColumnType.DATETIME:
        timestamp = pd.Timestamp(value)
        if timestamp.microsecond:
            return timestamp.isoformat(sep=" ")
        return timestamp.isoformat(sep=" ", timespec="seconds")
    if column_type == ColumnType.NUMBER:
        number = float(value)
        return format(number, ".15g")
    return str(value)


def json_value(value: Any, column_type: ColumnType) -> Any:
    if is_missing(value):
        return None
    if column_type == ColumnType.NUMBER:
        return float(value)
    if column_type == ColumnType.BOOLEAN:
        return bool(value)
    if column_type == ColumnType.DATETIME:
        return pd.Timestamp(value).isoformat()
    return str(value)


@dataclass(frozen=True)
class ColumnRef:
    project_id: str
    sheet_id: str
    column_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            "project_id": self.project_id,
            "sheet_id": self.sheet_id,
            "column_id": self.column_id,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ColumnRef":
        if not isinstance(value, dict):
            raise ValueError("Data reference must be an object.")
        fields = tuple(str(value.get(name, "")).strip() for name in ("project_id", "sheet_id", "column_id"))
        if not all(fields):
            raise ValueError("Data reference is missing an identifier.")
        return cls(*fields)


@dataclass
class ColumnSchema:
    id: str
    name: str
    type: ColumnType = ColumnType.AUTO
    width: int = DEFAULT_COLUMN_WIDTH

    def to_snapshot(self, values: pd.Series) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "width": int(self.width),
            "values": [json_value(value, self.type) for value in values],
        }


@dataclass
class SheetDocument:
    id: str
    name: str
    row_count: int = DEFAULT_ROWS
    columns: list[ColumnSchema] = field(default_factory=list)
    frame: pd.DataFrame = field(default_factory=pd.DataFrame)

    @classmethod
    def create(cls, name: str = "Sheet1", column_count: int = DEFAULT_COLUMNS) -> "SheetDocument":
        document = cls(id=new_id(), name=validate_component_name(name, "Sheet name"), row_count=DEFAULT_ROWS)
        for index in range(column_count):
            document.add_column(name=f"Column {index + 1}")
        return document

    @property
    def column_ids(self) -> list[str]:
        return [column.id for column in self.columns]

    def column_index(self, column_id: str) -> int:
        for index, column in enumerate(self.columns):
            if column.id == column_id:
                return index
        raise KeyError(f"Unknown column: {column_id}")

    def column(self, column_id: str) -> ColumnSchema:
        return self.columns[self.column_index(column_id)]

    def validate_column_name(self, name: str, exclude_id: str | None = None) -> str:
        cleaned = str(name).strip()
        if not cleaned:
            raise ValueError("Column name must not be empty.")
        normalized = cleaned.casefold()
        if any(column.id != exclude_id and column.name.casefold() == normalized for column in self.columns):
            raise ValueError(f"Column name already exists: {cleaned}")
        return cleaned

    def unique_column_name(self, preferred: str) -> str:
        base = str(preferred).strip() or f"Column {len(self.columns) + 1}"
        existing = {column.name.casefold() for column in self.columns}
        if base.casefold() not in existing:
            return base
        suffix = 2
        while f"{base} {suffix}".casefold() in existing:
            suffix += 1
        return f"{base} {suffix}"

    def _blank_series(self, column_type: ColumnType, count: int | None = None) -> pd.Series:
        length = self.row_count if count is None else max(0, int(count))
        if column_type == ColumnType.DATETIME:
            return pd.Series([pd.NaT] * length, dtype=PANDAS_DTYPES[column_type])
        if column_type == ColumnType.AUTO:
            return pd.Series([pd.NA] * length, dtype="object")
        return pd.Series([pd.NA] * length, dtype=PANDAS_DTYPES[column_type])

    def add_column(self, name: str | None = None, column_type: ColumnType = ColumnType.AUTO,
                   index: int | None = None, column_id: str | None = None,
                   width: int = DEFAULT_COLUMN_WIDTH, values: Sequence[Any] | None = None) -> ColumnSchema:
        name = self.validate_column_name(self.unique_column_name(name or f"Column {len(self.columns) + 1}"))
        raw = list(values) if values is not None else [pd.NA] * self.row_count
        if len(raw) > self.row_count:
            self.ensure_rows(len(raw))
        elif len(raw) < self.row_count:
            raw.extend([pd.NA] * (self.row_count - len(raw)))
        resolved = infer_column_type(raw) if column_type == ColumnType.AUTO else column_type
        target_id = column_id or new_id()
        if target_id in self.column_ids:
            raise ValueError(f"Column id already exists: {target_id}")
        schema = ColumnSchema(target_id, name, resolved, max(60, int(width)))
        series = coerce_series(raw, resolved)
        if index is None:
            index = len(self.columns)
        index = max(0, min(int(index), len(self.columns)))
        self.columns.insert(index, schema)
        self.frame[schema.id] = series
        self.frame = self.frame[self.column_ids]
        return schema

    def remove_column(self, column_id: str) -> tuple[int, ColumnSchema, pd.Series]:
        index = self.column_index(column_id)
        schema = self.columns.pop(index)
        values = self.frame.pop(column_id).copy(deep=True)
        return index, schema, values

    def restore_column(self, index: int, schema: ColumnSchema, values: pd.Series) -> None:
        self.columns.insert(index, schema)
        restored = values.reset_index(drop=True)
        if len(restored) < self.row_count:
            padding = self._blank_series(schema.type, self.row_count - len(restored))
            restored = pd.concat([restored, padding], ignore_index=True)
        self.frame[schema.id] = restored.iloc[: self.row_count].astype(
            PANDAS_DTYPES.get(schema.type, "object")
        )
        self.frame = self.frame[self.column_ids]

    def move_column(self, source: int, destination: int) -> None:
        if not 0 <= source < len(self.columns):
            raise IndexError("Column index is out of range.")
        destination = max(0, min(destination, len(self.columns) - 1))
        schema = self.columns.pop(source)
        self.columns.insert(destination, schema)
        self.frame = self.frame[self.column_ids]

    def ensure_rows(self, count: int) -> None:
        count = int(count)
        if count <= self.row_count:
            return
        add_count = count - self.row_count
        for column in self.columns:
            padding = self._blank_series(column.type, add_count)
            self.frame[column.id] = pd.concat([self.frame[column.id], padding], ignore_index=True)
        self.row_count = count

    def truncate_rows(self, count: int) -> None:
        count = max(0, min(int(count), self.row_count))
        if count == self.row_count:
            return
        self.frame = self.frame.iloc[:count].reset_index(drop=True)
        self.row_count = count

    def insert_rows(self, index: int, count: int = 1) -> None:
        index = max(0, min(int(index), self.row_count))
        count = max(1, int(count))
        for column in self.columns:
            series = self.frame[column.id]
            blanks = self._blank_series(column.type, count)
            self.frame[column.id] = pd.concat(
                [series.iloc[:index], blanks, series.iloc[index:]], ignore_index=True
            )
        self.row_count += count

    def remove_rows(self, index: int, count: int = 1) -> pd.DataFrame:
        if not 0 <= index < self.row_count:
            raise IndexError("Row index is out of range.")
        count = max(1, min(int(count), self.row_count - index))
        removed = self.frame.iloc[index:index + count].copy(deep=True)
        self.frame = pd.concat(
            [self.frame.iloc[:index], self.frame.iloc[index + count:]], ignore_index=True
        )
        self.row_count -= count
        return removed

    def restore_rows(self, index: int, rows: pd.DataFrame) -> None:
        index = max(0, min(int(index), self.row_count))
        restored = rows[self.column_ids].copy(deep=True)
        self.frame = pd.concat(
            [self.frame.iloc[:index], restored, self.frame.iloc[index:]], ignore_index=True
        )
        self.row_count = len(self.frame)

    def move_row(self, source: int, destination: int) -> None:
        if not 0 <= source < self.row_count:
            raise IndexError("Row index is out of range.")
        destination = max(0, min(int(destination), self.row_count - 1))
        if source == destination:
            return
        order = list(range(self.row_count))
        row = order.pop(source)
        order.insert(destination, row)
        self.frame = self.frame.iloc[order].reset_index(drop=True)

    def resolved_edit(self, column_id: str, values: Sequence[Any]) -> tuple[ColumnType, list[Any]]:
        schema = self.column(column_id)
        resolved = schema.type
        if resolved == ColumnType.AUTO:
            resolved = infer_column_type(values)
            if resolved == ColumnType.AUTO:
                return resolved, [pd.NA for _ in values]
        return resolved, [coerce_value(value, resolved) for value in values]

    def set_cell(self, row: int, column_id: str, value: Any) -> tuple[Any, ColumnType]:
        if not 0 <= row < self.row_count:
            raise IndexError("Row index is out of range.")
        schema = self.column(column_id)
        resolved, values = self.resolved_edit(column_id, [value])
        old_value = self.frame.at[row, column_id]
        if schema.type == ColumnType.AUTO and resolved != ColumnType.AUTO:
            schema.type = resolved
            self.frame[column_id] = self.frame[column_id].astype(PANDAS_DTYPES[resolved])
        self.frame.at[row, column_id] = values[0]
        return old_value, resolved

    def set_block(self, start_row: int, start_column: int,
                  rows: Sequence[Sequence[Any]]) -> tuple[pd.DataFrame, list[ColumnType]]:
        block = [list(row) for row in rows]
        if not block:
            return pd.DataFrame(), []
        width = max((len(row) for row in block), default=0)
        if width == 0:
            return pd.DataFrame(), []
        for row in block:
            row.extend([""] * (width - len(row)))
        self.ensure_rows(start_row + len(block))
        while start_column + width > len(self.columns):
            self.add_column()

        target_ids = self.column_ids[start_column:start_column + width]
        converted_by_column: list[list[Any]] = []
        resolved_types: list[ColumnType] = []
        for offset, column_id in enumerate(target_ids):
            incoming = [row[offset] for row in block]
            resolved, converted = self.resolved_edit(column_id, incoming)
            resolved_types.append(resolved)
            converted_by_column.append(converted)

        old = self.frame.loc[start_row:start_row + len(block) - 1, target_ids].copy(deep=True)
        for offset, column_id in enumerate(target_ids):
            schema = self.column(column_id)
            resolved = resolved_types[offset]
            if schema.type == ColumnType.AUTO and resolved != ColumnType.AUTO:
                schema.type = resolved
                self.frame[column_id] = self.frame[column_id].astype(PANDAS_DTYPES[resolved])
            self.frame.loc[start_row:start_row + len(block) - 1, column_id] = converted_by_column[offset]
        return old, resolved_types

    def replace_block(self, start_row: int, column_ids: Sequence[str], values: pd.DataFrame,
                      types: Sequence[ColumnType] | None = None) -> None:
        if types is not None:
            for column_id, column_type in zip(column_ids, types):
                schema = self.column(column_id)
                schema.type = column_type
                self.frame[column_id] = self.frame[column_id].astype(
                    PANDAS_DTYPES.get(column_type, "object")
                )
        stop = start_row + len(values) - 1
        self.frame.loc[start_row:stop, list(column_ids)] = values[list(column_ids)].to_numpy()

    def convert_column(self, column_id: str, target: ColumnType) -> tuple[ColumnType, pd.Series]:
        if target == ColumnType.AUTO and self.frame[column_id].notna().any():
            raise ValueError("Only an empty column can use the automatic type.")
        schema = self.column(column_id)
        old_type = schema.type
        old_values = self.frame[column_id].copy(deep=True)
        converted = coerce_series(old_values, target)
        resolved = infer_column_type(old_values) if target == ColumnType.AUTO else target
        schema.type = resolved
        self.frame[column_id] = converted
        return old_type, old_values

    def sort_rows(self, column_id: str, ascending: bool = True) -> list[int]:
        series = self.frame[column_id]
        ordered = series.sort_values(ascending=ascending, na_position="last", kind="stable").index.tolist()
        self.frame = self.frame.loc[ordered].reset_index(drop=True)
        return ordered

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "row_count": int(self.row_count),
            "columns": [column.to_snapshot(self.frame[column.id]) for column in self.columns],
        }

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any]) -> "SheetDocument":
        sheet_id = str(snapshot.get("id", "")).strip()
        if not sheet_id:
            raise ValueError("Sheet id must not be empty.")
        sheet = cls(
            id=sheet_id,
            name=str(snapshot["name"]),
            row_count=max(0, int(snapshot.get("row_count", 0))),
        )
        columns = snapshot.get("columns", [])
        if not isinstance(columns, list):
            raise ValueError("Sheet columns must be an array.")
        for column_snapshot in columns:
            column_id = str(column_snapshot.get("id", "")).strip()
            if not column_id:
                raise ValueError("Column id must not be empty.")
            column_type = ColumnType(column_snapshot["type"])
            values = list(column_snapshot.get("values", []))
            if len(values) != sheet.row_count:
                raise ValueError("Column value count does not match sheet row_count.")
            sheet.add_column(
                name=column_snapshot["name"],
                column_type=column_type,
                column_id=column_id,
                width=int(column_snapshot.get("width", DEFAULT_COLUMN_WIDTH)),
                values=values,
            )
        return sheet


@dataclass
class ProjectTableDocument:
    id: str
    name: str
    sheets: "OrderedDict[str, SheetDocument]" = field(default_factory=OrderedDict)

    @classmethod
    def create(cls, name: str, first_sheet_name: str = "Sheet1") -> "ProjectTableDocument":
        project = cls(id=new_id(), name=validate_component_name(name, "Project name"))
        sheet = SheetDocument.create(first_sheet_name)
        project.sheets[sheet.id] = sheet
        return project

    def sheet_by_name(self, name: str) -> SheetDocument:
        normalized = str(name).strip().casefold()
        for sheet in self.sheets.values():
            if sheet.name.casefold() == normalized:
                return sheet
        raise KeyError(f"Unknown sheet: {name}")

    def unique_sheet_name(self, preferred: str) -> str:
        base = str(preferred).strip() or f"Sheet{len(self.sheets) + 1}"
        existing = {sheet.name.casefold() for sheet in self.sheets.values()}
        if base.casefold() not in existing:
            return base
        suffix = 2
        while f"{base} {suffix}".casefold() in existing:
            suffix += 1
        return f"{base} {suffix}"

    def add_sheet(self, name: str | None = None, sheet: SheetDocument | None = None) -> SheetDocument:
        if sheet is None:
            sheet = SheetDocument.create(validate_component_name(
                self.unique_sheet_name(name or f"Sheet{len(self.sheets) + 1}"), "Sheet name"
            ))
        elif any(existing.name.casefold() == sheet.name.casefold() for existing in self.sheets.values()):
            raise ValueError(f"Sheet name already exists: {sheet.name}")
        if sheet.id in self.sheets:
            raise ValueError(f"Sheet id already exists: {sheet.id}")
        self.sheets[sheet.id] = sheet
        return sheet

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "sheets": [sheet.to_snapshot() for sheet in self.sheets.values()],
        }

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any]) -> "ProjectTableDocument":
        project = cls(id=str(snapshot["id"]), name=str(snapshot["name"]))
        sheets = snapshot.get("sheets", [])
        if not isinstance(sheets, list):
            raise ValueError("Project sheets must be an array.")
        for sheet_snapshot in sheets:
            sheet = SheetDocument.from_snapshot(sheet_snapshot)
            project.add_sheet(sheet=sheet)
        if not project.sheets:
            project.add_sheet(name="Sheet1")
        return project
