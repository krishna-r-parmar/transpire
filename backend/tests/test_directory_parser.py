import io

import pytest
from openpyxl import Workbook

from app.domains.directory.parser import ReportFormatError, parse_report

HEADER = [
    "Username",
    "First Name",
    "Middle Name",
    "Last Name",
    "Location  Name",
    "Department Name",
    "Sub-Department Name",
    "Business  Email Information Email Address",
    "Manager User Sys ID",
    "Manager",
    "HOD  Job Relationships User ID",
    "HOD  Job Relationships Name",
]


def workbook(rows: list[list[object]]) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "Report_Anything"
    sheet.append(HEADER)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_reads_padded_headers_numeric_ids_and_leading_zeros() -> None:
    content = workbook(
        [
            [
                350395.0,
                "Umang",
                "K.",
                "Prajapati",
                "Bavla",
                "Scale-up",
                "Unit - 06",
                " Umang@Example.com ",
                303359,
                "Patel, R",
                "302992",
                "Patel, A",
            ],
            ["007", "Bond", "", "James", "", "", "", "", "", "", "", ""],
        ]
    )
    report = parse_report(content, "report.xlsx")
    first, second = report.rows
    assert first.employee_id == "350395"
    assert first.manager_employee_id == "303359"
    assert first.email == "umang@example.com"
    assert first.display_name == "Umang Prajapati"
    assert second.employee_id == "007"
    assert second.email is None and second.manager_employee_id is None


def test_flags_duplicates_bad_emails_and_self_management() -> None:
    content = workbook(
        [
            ["1", "A", "", "One", "", "", "", "a@example.com", "1", "", "1", ""],
            ["1", "A", "", "Again", "", "", "", "", "", "", "", ""],
            ["2", "B", "", "Two", "", "", "", "not-an-email", "", "", "", ""],
            ["3", "C", "", "Three", "", "", "", "A@example.com", "", "", "", ""],
        ]
    )
    report = parse_report(content, "report.xlsx")
    assert [row.employee_id for row in report.rows] == ["1", "2", "3"]
    assert report.rows[0].manager_employee_id is None and report.rows[0].hod_employee_id is None
    assert report.rows[1].email is None
    assert report.rows[2].email is None  # email already used by employee 1
    messages = " ".join(issue.message for issue in report.issues)
    assert "Duplicate employee ID" in messages and "own manager" in messages


def test_unchanged_rows_hash_identically_and_changes_do_not() -> None:
    row = ["9", "Z", "", "Zed", "Bavla", "Ops", "", "z@example.com", "1", "", "2", ""]
    one = parse_report(workbook([row]), "a.xlsx").rows[0]
    same = parse_report(workbook([row]), "b.xlsx").rows[0]
    moved = parse_report(workbook([[*row[:8], "5", *row[9:]]]), "c.xlsx").rows[0]
    assert one.row_hash == same.row_hash
    assert one.row_hash != moved.row_hash


def test_rejects_unreadable_or_incomplete_files() -> None:
    with pytest.raises(ReportFormatError, match="Required columns"):
        parse_report(b"Username,First Name\n1,A\n", "report.csv")
    with pytest.raises(ReportFormatError, match="xlsx or .csv"):
        parse_report(b"x", "report.pdf")
    with pytest.raises(ReportFormatError, match="readable Excel"):
        parse_report(b"not a zip", "report.xlsx")
