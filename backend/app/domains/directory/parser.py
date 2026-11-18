"""Read the HR employee report (xlsx or csv) into normalised, hashed rows.

The report's headers are matched by normalised name (spaces collapsed, case ignored), never
by position: the source system pads some headers with double spaces. IDs are read as text so
leading zeros survive and numeric cells such as ``350395.0`` become ``350395``.
"""

import csv
import hashlib
import io
import json
import re
from dataclasses import asdict, dataclass, field

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ROWS = 50_000
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# canonical field -> accepted normalised header names
HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "employee_id": ("username", "user id", "employee id", "employee code"),
    "first_name": ("first name",),
    "middle_name": ("middle name",),
    "last_name": ("last name",),
    "location": ("location name", "location"),
    "department": ("department name", "department"),
    "sub_department": ("sub-department name", "sub department name", "sub-department"),
    "email": (
        "business email information email address",
        "business email",
        "email address",
        "email",
    ),
    "manager_employee_id": ("manager user sys id", "manager user id", "manager id"),
    "hod_employee_id": ("hod job relationships user id", "hod user id", "hod id"),
}
REQUIRED_FIELDS = ("employee_id", "first_name", "email", "manager_employee_id", "hod_employee_id")
HASHED_FIELDS = (
    "first_name",
    "middle_name",
    "last_name",
    "email",
    "location",
    "department",
    "sub_department",
    "manager_employee_id",
    "hod_employee_id",
)


class ReportFormatError(ValueError):
    """The file cannot be read as an HR report at all."""


@dataclass
class EmployeeRow:
    line: int
    employee_id: str
    first_name: str = ""
    middle_name: str = ""
    last_name: str = ""
    email: str | None = None
    location: str = ""
    department: str = ""
    sub_department: str = ""
    manager_employee_id: str | None = None
    hod_employee_id: str | None = None
    row_hash: str = ""

    @property
    def display_name(self) -> str:
        return " ".join(part for part in (self.first_name, self.last_name) if part) or (
            self.employee_id
        )

    def fingerprint(self) -> str:
        payload = {name: getattr(self, name) for name in HASHED_FIELDS}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


@dataclass
class RowIssue:
    line: int
    employee_id: str | None
    severity: str  # "error" drops the row, "warning" keeps it
    message: str


@dataclass
class ParsedReport:
    rows: list[EmployeeRow] = field(default_factory=list)
    issues: list[RowIssue] = field(default_factory=list)

    def issue_dicts(self) -> list[dict[str, object]]:
        return [asdict(issue) for issue in self.issues]


def normalise_header(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def clean_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return re.sub(r"\s+", " ", str(value)).strip()


def clean_id(value: object) -> str | None:
    text = clean_text(value)
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", 1)[0]
    return text or None


def _rows_from_xlsx(content: bytes) -> list[list[object]]:
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as error:  # openpyxl raises many types for unreadable files
        raise ReportFormatError("The file is not a readable Excel workbook.") from error
    try:
        sheet = workbook.worksheets[0]
        rows: list[list[object]] = []
        for row in sheet.iter_rows(values_only=True):
            rows.append(list(row))
            if len(rows) > MAX_ROWS + 1:
                raise ReportFormatError(f"The file has more than {MAX_ROWS} rows.")
        return rows
    finally:
        workbook.close()


def _rows_from_csv(content: bytes) -> list[list[object]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("cp1252", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) > MAX_ROWS + 1:
        raise ReportFormatError(f"The file has more than {MAX_ROWS} rows.")
    return rows


def parse_report(content: bytes, file_name: str) -> ParsedReport:
    if not content:
        raise ReportFormatError("The file is empty.")
    if len(content) > MAX_FILE_BYTES:
        raise ReportFormatError("The file is larger than 10 MB.")
    lowered = file_name.casefold()
    if lowered.endswith(".xlsx"):
        raw = _rows_from_xlsx(content)
    elif lowered.endswith(".csv"):
        raw = _rows_from_csv(content)
    else:
        raise ReportFormatError("Upload an .xlsx or .csv file.")

    raw = [row for row in raw if any(clean_text(cell) for cell in row)]
    if not raw:
        raise ReportFormatError("The file has no header row.")
    headers = [normalise_header(cell) for cell in raw[0]]
    columns: dict[str, int] = {}
    for field_name, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if alias in headers:
                columns[field_name] = headers.index(alias)
                break
    missing = [name for name in REQUIRED_FIELDS if name not in columns]
    if missing:
        readable = ", ".join(HEADER_ALIASES[name][0].title() for name in missing)
        raise ReportFormatError(f"Required columns are missing: {readable}.")

    report = ParsedReport()
    seen_ids: set[str] = set()
    seen_emails: dict[str, str] = {}
    for offset, values in enumerate(raw[1:], start=2):

        def cell(name: str, values: list[object] = values) -> object:
            index = columns.get(name)
            return values[index] if index is not None and index < len(values) else None

        employee_id = clean_id(cell("employee_id"))
        if not employee_id:
            report.issues.append(RowIssue(offset, None, "error", "Missing employee ID (Username)."))
            continue
        if employee_id in seen_ids:
            report.issues.append(
                RowIssue(offset, employee_id, "error", "Duplicate employee ID; first row kept.")
            )
            continue
        seen_ids.add(employee_id)
        row = EmployeeRow(
            line=offset,
            employee_id=employee_id,
            first_name=clean_text(cell("first_name")),
            middle_name=clean_text(cell("middle_name")),
            last_name=clean_text(cell("last_name")),
            location=clean_text(cell("location")),
            department=clean_text(cell("department")),
            sub_department=clean_text(cell("sub_department")),
            manager_employee_id=clean_id(cell("manager_employee_id")),
            hod_employee_id=clean_id(cell("hod_employee_id")),
        )
        email = clean_text(cell("email")).casefold()
        if email and not EMAIL_PATTERN.match(email):
            report.issues.append(
                RowIssue(offset, employee_id, "warning", f"Invalid email '{email}' ignored.")
            )
            email = ""
        if email and email in seen_emails:
            report.issues.append(
                RowIssue(
                    offset,
                    employee_id,
                    "warning",
                    f"Email also used by employee {seen_emails[email]}; ignored for this row.",
                )
            )
            email = ""
        if email:
            seen_emails[email] = employee_id
        row.email = email or None
        if row.manager_employee_id == employee_id:
            report.issues.append(
                RowIssue(offset, employee_id, "warning", "Listed as their own manager; ignored.")
            )
            row.manager_employee_id = None
        if row.hod_employee_id == employee_id:
            row.hod_employee_id = None  # The head of department has no HoD above them.
        row.row_hash = row.fingerprint()
        report.rows.append(row)
    return report
