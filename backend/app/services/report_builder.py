"""
Builds report FILE BYTES from already-aggregated analytics data.

These are point-in-time snapshot exports for HR to download/share, not
editable templates — every number is a static value baked in at generation
time, deliberately (a live formula would be wrong the moment someone reopens
last quarter's PDF a year later and it recalculates against today's data).

Two formats:
  - PDF   (reportlab)   -> narrative report with tables
  - EXCEL (xlsxwriter)  -> one sheet per section, for HR to pivot/filter further
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from app.schemas.analytics import AnalyticsResponse


def _section_title(scope_label: str) -> str:
    return f"Exit Interview Report — {scope_label}"


def build_pdf_report(
    *, scope_label: str, generated_at: datetime, analytics: AnalyticsResponse, campaign_meta: dict[str, Any] | None
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.75 * inch, bottomMargin=0.75 * inch)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(_section_title(scope_label), styles["Title"]))
    story.append(Paragraph(f"Generated {generated_at.strftime('%Y-%m-%d %H:%M UTC')}", styles["Normal"]))
    story.append(Spacer(1, 0.25 * inch))

    if campaign_meta:
        story.append(Paragraph("Campaign Summary", styles["Heading2"]))
        campaign_rows = [
            ["Name", campaign_meta.get("name", "")],
            ["Status", campaign_meta.get("status", "")],
            ["Window", f"{campaign_meta.get('start_at', '')} to {campaign_meta.get('end_at', '')}"],
        ]
        table = Table(campaign_rows, colWidths=[1.5 * inch, 5 * inch])
        table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold")]))
        story.append(table)
        story.append(Spacer(1, 0.25 * inch))

    story.append(Paragraph("Participation & Completion", styles["Heading2"]))
    story.append(
        Table(
            [
                ["Total Assigned", str(analytics.total_assigned)],
                ["Total Completed", str(analytics.total_completed)],
                ["Completion Rate", f"{analytics.completion_rate}%"],
                [
                    "Overall Satisfaction",
                    f"{analytics.overall_satisfaction}/10" if analytics.overall_satisfaction is not None else "N/A",
                ],
            ],
            colWidths=[2.5 * inch, 4 * inch],
            style=TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey)]),
        )
    )
    story.append(Spacer(1, 0.25 * inch))

    story.append(Paragraph("Department Analysis", styles["Heading2"]))
    dept_data = [["Department", "Assigned", "Completed", "Participation", "Avg. Satisfaction"]]
    sat_by_dept = {d.department: d for d in analytics.department_satisfaction}
    for dept in analytics.department_participation:
        sat = sat_by_dept.get(dept.department)
        dept_data.append(
            [
                dept.department,
                str(dept.assigned_count),
                str(dept.completed_count),
                f"{dept.participation_rate}%",
                f"{sat.average_satisfaction}/10" if sat and sat.average_satisfaction is not None else "N/A",
            ]
        )
    dept_table = Table(dept_data, colWidths=[1.6 * inch] * 5)
    dept_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        )
    )
    story.append(dept_table)
    story.append(Spacer(1, 0.25 * inch))

    for heading, items, label_key in (
        ("Common Exit Reasons", analytics.common_exit_reasons, "reason"),
        ("Common Themes", analytics.common_themes, "theme"),
        ("Recommendations", analytics.recommendations, "recommendation"),
    ):
        story.append(Paragraph(heading, styles["Heading2"]))
        if items:
            rows = [[label_key.capitalize(), "Mentions"]] + [[i.label, str(i.count)] for i in items]
            t = Table(rows, colWidths=[4.5 * inch, 1.5 * inch])
            t.setStyle(
                TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ]
                )
            )
            story.append(t)
        else:
            story.append(Paragraph("No data available.", styles["Normal"]))
        story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("Key Comments", styles["Heading2"]))
    if analytics.key_comments:
        for comment in analytics.key_comments:
            story.append(Paragraph(f"“{comment}”", styles["Normal"]))
            story.append(Spacer(1, 0.08 * inch))
    else:
        story.append(
            Paragraph(
                "Withheld: not enough completed interviews yet to share comments without risking "
                "identifying an individual respondent.",
                styles["Italic"],
            )
        )

    doc.build(story)
    return buffer.getvalue()


def build_excel_report(
    *, scope_label: str, generated_at: datetime, analytics: AnalyticsResponse, campaign_meta: dict[str, Any] | None
) -> bytes:
    import xlsxwriter

    buffer = io.BytesIO()
    workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})

    header_fmt = workbook.add_format({"bold": True, "bg_color": "#F0F0F0", "border": 1, "font_name": "Arial"})
    cell_fmt = workbook.add_format({"border": 1, "font_name": "Arial"})
    title_fmt = workbook.add_format({"bold": True, "font_size": 14, "font_name": "Arial"})

    summary = workbook.add_worksheet("Summary")
    summary.set_column(0, 1, 28)
    summary.write(0, 0, _section_title(scope_label), title_fmt)
    summary.write(1, 0, f"Generated {generated_at.strftime('%Y-%m-%d %H:%M UTC')}")

    row = 3
    if campaign_meta:
        for label, value in (
            ("Campaign", campaign_meta.get("name", "")),
            ("Status", campaign_meta.get("status", "")),
            ("Start", str(campaign_meta.get("start_at", ""))),
            ("End", str(campaign_meta.get("end_at", ""))),
        ):
            summary.write(row, 0, label, header_fmt)
            summary.write(row, 1, value, cell_fmt)
            row += 1
        row += 1

    for label, value in (
        ("Total Assigned", analytics.total_assigned),
        ("Total Completed", analytics.total_completed),
        ("Completion Rate (%)", analytics.completion_rate),
        ("Overall Satisfaction (/10)", analytics.overall_satisfaction if analytics.overall_satisfaction is not None else "N/A"),
    ):
        summary.write(row, 0, label, header_fmt)
        summary.write(row, 1, value, cell_fmt)
        row += 1

    dept_sheet = workbook.add_worksheet("Departments")
    dept_sheet.set_column(0, 4, 20)
    headers = ["Department", "Assigned", "Completed", "Participation (%)", "Avg. Satisfaction"]
    for col, h in enumerate(headers):
        dept_sheet.write(0, col, h, header_fmt)
    sat_by_dept = {d.department: d for d in analytics.department_satisfaction}
    for i, dept in enumerate(analytics.department_participation, start=1):
        sat = sat_by_dept.get(dept.department)
        dept_sheet.write(i, 0, dept.department, cell_fmt)
        dept_sheet.write(i, 1, dept.assigned_count, cell_fmt)
        dept_sheet.write(i, 2, dept.completed_count, cell_fmt)
        dept_sheet.write(i, 3, dept.participation_rate, cell_fmt)
        dept_sheet.write(i, 4, sat.average_satisfaction if sat and sat.average_satisfaction is not None else "N/A", cell_fmt)

    for sheet_name, items, label_header in (
        ("Exit Reasons", analytics.common_exit_reasons, "Reason"),
        ("Themes", analytics.common_themes, "Theme"),
        ("Recommendations", analytics.recommendations, "Recommendation"),
    ):
        sheet = workbook.add_worksheet(sheet_name)
        sheet.set_column(0, 0, 40)
        sheet.set_column(1, 1, 12)
        sheet.write(0, 0, label_header, header_fmt)
        sheet.write(0, 1, "Mentions", header_fmt)
        for i, item in enumerate(items, start=1):
            sheet.write(i, 0, item.label, cell_fmt)
            sheet.write(i, 1, item.count, cell_fmt)

    comments_sheet = workbook.add_worksheet("Key Comments")
    comments_sheet.set_column(0, 0, 80)
    comments_sheet.write(0, 0, "Comment", header_fmt)
    if analytics.key_comments:
        for i, comment in enumerate(analytics.key_comments, start=1):
            comments_sheet.write(i, 0, comment, cell_fmt)
    else:
        comments_sheet.write(
            1, 0, "Withheld: not enough completed interviews yet to share comments without risking identification."
        )

    workbook.close()
    return buffer.getvalue()
