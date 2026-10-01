"""
Parses uploaded employee files (.xlsx, .xls, .csv, .pdf) into a uniform list
of raw row dicts with canonical keys:

    name, email, employee_id, department, designation, last_working_date

Header matching is case-insensitive and tolerant of the human-friendly
column names HR is likely to use in a spreadsheet (e.g. "Employee ID",
"Last Working Date"). Values are NOT validated here — validation (required
fields, email format, date parsing, duplicates) happens in import_service.
This module's only job is turning bytes into raw strings per row.
"""
from __future__ import annotations

import csv
import io
from typing import Any

from app.core.exceptions import ImportValidationFailedError

_HEADER_ALIASES: dict[str, str] = {
    "name": "name",
    "full name": "name",
    "employee name": "name",
    "email": "email",
    "email address": "email",
    "employee id": "employee_id",
    "employeeid": "employee_id",
    "emp id": "employee_id",
    "emp_id": "employee_id",
    "id": "employee_id",
    "department": "department",
    "dept": "department",
    "designation": "designation",
    "title": "designation",
    "job title": "designation",
    "last working date": "last_working_date",
    "last_working_date": "last_working_date",
    "lwd": "last_working_date",
    "exit date": "last_working_date",
}

CANONICAL_FIELDS = ("name", "email", "employee_id", "department", "designation", "last_working_date")


def _normalize_header(raw_header: str) -> str | None:
    key = raw_header.strip().lower()
    return _HEADER_ALIASES.get(key)


def _remap_row(raw_row: dict[str, Any], header_map: dict[str, str]) -> dict[str, Any]:
    remapped: dict[str, Any] = {field: None for field in CANONICAL_FIELDS}
    for raw_key, canonical in header_map.items():
        value = raw_row.get(raw_key)
        if value is None:
            continue
        # pandas may parse date-like Excel cells into Timestamp/datetime
        # objects rather than plain strings — normalize those to ISO date
        # strings so downstream date parsing (which expects strings) works
        # the same regardless of source format.
        if hasattr(value, "strftime"):
            value = value.strftime("%Y-%m-%d")
        else:
            value = str(value).strip()
            if value.lower() == "nan":
                value = ""
        remapped[canonical] = value if value != "" else None
    return remapped


def _build_header_map(raw_headers: list[str]) -> dict[str, str]:
    header_map: dict[str, str] = {}
    for raw_header in raw_headers:
        canonical = _normalize_header(str(raw_header))
        if canonical:
            header_map[raw_header] = canonical
    missing = set(("name", "email", "employee_id")) - set(header_map.values())
    if missing:
        raise ImportValidationFailedError(
            "The uploaded file is missing required column(s): " + ", ".join(sorted(missing))
        )
    return header_map


def parse_csv(file_bytes: bytes) -> list[dict[str, Any]]:
    text = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ImportValidationFailedError("The uploaded CSV file appears to be empty.")

    header_map = _build_header_map(list(reader.fieldnames))
    rows = [_remap_row(row, header_map) for row in reader]
    return rows


def parse_excel(file_bytes: bytes) -> list[dict[str, Any]]:
    import pandas as pd

    try:
        df = pd.read_excel(io.BytesIO(file_bytes))
    except Exception as exc:  # pragma: no cover - depends on corrupt input
        raise ImportValidationFailedError("Could not read the uploaded Excel file. Is it corrupted?") from exc

    if df.empty:
        raise ImportValidationFailedError("The uploaded Excel file appears to be empty.")

    header_map = _build_header_map(list(df.columns))
    df = df.where(pd.notnull(df), None)
    rows = [_remap_row(row, header_map) for row in df.to_dict(orient="records")]
    return rows


def parse_pdf(file_bytes: bytes) -> list[dict[str, Any]]:
    """
    Best-effort table extraction from a PDF: expects a simple table with a
    single header row, optionally repeated at the top of subsequent pages
    (common when a table spans multiple pages).
    """
    import pdfplumber

    all_rows: list[dict[str, Any]] = []
    raw_headers: list[str] | None = None
    header_map: dict[str, str] | None = None

    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
                    if not table:
                        continue
                    if raw_headers is None:
                        raw_headers = [str(h or "") for h in table[0]]
                        header_map = _build_header_map(raw_headers)
                        data_rows = table[1:]
                    else:
                        # Skip a repeated header row on subsequent pages.
                        first_row = [str(c or "").strip().lower() for c in table[0]]
                        expected = [h.strip().lower() for h in raw_headers]
                        data_rows = table[1:] if first_row == expected else table

                    for raw_row in data_rows:
                        row_dict = dict(zip(raw_headers, raw_row))
                        all_rows.append(_remap_row(row_dict, header_map))
    except ImportValidationFailedError:
        raise
    except Exception as exc:  # pragma: no cover - depends on corrupt input
        raise ImportValidationFailedError("Could not read the uploaded PDF file. Is it corrupted?") from exc

    if header_map is None or not all_rows:
        raise ImportValidationFailedError(
            "No employee data table could be found in the uploaded PDF. "
            "PDF import expects a simple table with a header row."
        )
    return all_rows


def parse_employee_file(file_bytes: bytes, extension: str) -> list[dict[str, Any]]:
    extension = extension.lower()
    if extension == ".csv":
        return parse_csv(file_bytes)
    if extension in (".xlsx", ".xls"):
        return parse_excel(file_bytes)
    if extension == ".pdf":
        return parse_pdf(file_bytes)
    raise ImportValidationFailedError(f"Unsupported file extension: {extension}")
