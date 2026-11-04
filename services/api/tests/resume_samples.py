"""A made-up, deliberately messy resume, built in code for the import tests.

Jordan Rivera is fictional. Every problem the audit looks for is planted here
on purpose: contact details in the page header, a skills table, a text box,
mixed bullets, date formats and header orders, a tense slip, a gap, an
overlap, a duplicated bullet, an objective and a references line.
"""

import io
from typing import Any

from docx import Document
from docx.enum.text import WD_BREAK
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from docx.shared import Pt
from fpdf import FPDF

NAME = "Jordan Rivera"
HEADER = "412 Elm Street, Columbus, OH 43215 | (614) 555-0182 | jordan.rivera@example.com"

ROLES: list[dict[str, Any]] = [
    {
        "header": "Senior Financial Analyst, Northwind Logistics\t03/2021 – Present",
        "bullets": [
            "Lead the monthly close for 6 business units, cutting close time from 10 to 6 days.",
            "Responsible for budget variance reporting",
            "Built a forecasting model in Python that improved accuracy by 12%.",
        ],
        "glyph": None,
    },
    {
        "header": "Contoso Health — Financial Analyst\tJan 2018 - Feb 2021",
        "bullets": [
            "Manage accounts payable reconciliations for $40M in annual spend.",
            "Helped with audit preparation",
            "Built a forecasting model in Python that improved accuracy by 12%.",
        ],
        "glyph": "-",
    },
    {
        "header": "Volunteer Treasurer, Riverside Food Bank\tJun 2019 – Dec 2020",
        "bullets": ["Kept the books for a $250K annual budget."],
        "glyph": "•",
    },
    {
        "header": "Staff Accountant\nFabrikam Inc.\n2014 to 2016",
        "bullets": ["Prepared journal entries.", "Reconciled bank accounts"],
        "glyph": "▪",
    },
]

TEXT_BOX = (
    f"<w:p {nsdecls('w')} xmlns:v='urn:schemas-microsoft-com:vml'>"
    "<w:r><w:pict><v:shape style='width:200pt;height:40pt'><v:textbox>"
    "<w:txbxContent><w:p><w:r><w:t>Certifications: CPA (Ohio), 2017</w:t></w:r></w:p>"
    "</w:txbxContent></v:textbox></v:shape></w:pict></w:r></w:p>"
)


def messy_docx() -> bytes:
    doc = Document()
    styles: Any = doc.styles
    styles["Normal"].font.name = "Calibri"
    styles["Normal"].font.size = Pt(11)

    header = doc.sections[0].header.paragraphs[0]
    header.text = f"{NAME} | {HEADER}"

    _heading(doc, "OBJECTIVE")
    doc.add_paragraph(
        "Results-driven finance professional seeking a challenging role where I can "
        "leverage my skills in a dynamic team."
    )

    doc.add_heading("Professional Experience", level=1)
    for i, role in enumerate(ROLES):
        lines = role["header"].split("\n")
        para = doc.add_paragraph()
        for j, line in enumerate(lines):
            run = para.add_run(line)
            run.bold = True
            if i == 1:
                run.font.name = "Arial"
                run.font.size = Pt(10.5)
            if j < len(lines) - 1:
                run.add_break(WD_BREAK.LINE)
        for bullet in role["bullets"]:
            if role["glyph"] is None:
                doc.add_paragraph(bullet, style="List Bullet")
            else:
                doc.add_paragraph(f"{role['glyph']} {bullet}")

    _heading(doc, "Education")
    doc.add_paragraph("B.S. Accounting, Ohio State University, 2014")

    _heading(doc, "SKILLS")
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Excel, SQL, Python"
    table.cell(0, 1).text = "SAP, Oracle Hyperion"

    doc.element.body.insert(len(doc.element.body) - 1, parse_xml(TEXT_BOX))
    doc.add_paragraph("References available upon request")

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def _heading(doc: Any, text: str) -> None:
    run = doc.add_paragraph().add_run(text)
    run.bold = True


def messy_text() -> str:
    lines = [NAME, HEADER, "", "OBJECTIVE", "Results-driven finance professional.", ""]
    lines.append("PROFESSIONAL EXPERIENCE")
    for role in ROLES:
        lines.extend(role["header"].split("\n"))
        lines.extend(f"{role['glyph'] or '•'} {b}" for b in role["bullets"])
        lines.append("")
    lines += ["EDUCATION", "B.S. Accounting, Ohio State University, 2014", ""]
    lines += ["SKILLS", "Excel, SQL, Python, SAP, Oracle Hyperion"]
    return "\n".join(lines)


# "•" in the PDF core fonts' WinAnsi encoding; it reads back as U+2022.
PDF_BULLET = chr(149)


def clean_pdf() -> bytes:
    """A tidy one-column PDF, to check that PDFs read in order with bullets."""
    pdf = FPDF(format="Letter")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 8, "Avery Chen", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(
        0, 6, "Seattle, WA | avery.chen@example.com | (206) 555-0147", new_x="LMARGIN", new_y="NEXT"
    )
    sections = [
        ("EXPERIENCE", None),
        ("Product Manager, Tailspin Toys", "Apr 2020 - Present"),
        ("- Launched a subscription plan that grew revenue 18% in its first year.", None),
        ("- Led a team of 7 engineers and 2 designers through 14 releases.", None),
        ("Associate Product Manager, Adventure Works", "Jun 2017 - Mar 2020"),
        ("- Cut checkout drop-off by 9% by rebuilding the payment flow.", None),
        ("EDUCATION", None),
        ("B.A. Economics, University of Washington", "2017"),
        ("SKILLS", None),
        ("Roadmapping, SQL, A/B testing, Figma", None),
    ]
    for text, right in sections:
        heading = text.isupper()
        pdf.set_font("Helvetica", "B" if heading or right else "", 11 if heading else 10)
        if heading:
            pdf.ln(3)
        if text.startswith("- "):
            pdf.set_font("Helvetica", "", 10)
            text = PDF_BULLET + text[1:]
        pdf.cell(
            130 if right else 0,
            6,
            text,
            new_x="RIGHT" if right else "LMARGIN",
            new_y="TOP" if right else "NEXT",
        )
        if right:
            pdf.cell(0, 6, right, align="R", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def two_column_pdf() -> bytes:
    """A sidebar layout: contact and skills on the left, experience on the right."""
    pdf = FPDF(format="Letter")
    pdf.add_page()
    left = [
        "CONTACT",
        "Sam Okafor",
        "Austin, TX",
        "sam.okafor@example.com",
        "(512) 555-0110",
        "SKILLS",
        "Salesforce",
        "Forecasting",
        "Negotiation",
        "Territory planning",
        "HubSpot",
        "Excel",
    ]
    right = [
        "EXPERIENCE",
        "Account Executive, Litware Inc.",
        "Feb 2022 - Present",
        PDF_BULLET + " Closed $3.1M in new business in fiscal 2024.",
        PDF_BULLET + " Grew the mid-market book from 40 to 65 accounts.",
        "Sales Development Rep, Proseware",
        "Jul 2019 - Jan 2022",
        PDF_BULLET + " Booked 310 qualified meetings across two years.",
        PDF_BULLET + " Trained 6 new reps on the outbound playbook.",
        "EDUCATION",
        "B.B.A. Marketing, University of Texas",
        "2019",
    ]
    for i in range(max(len(left), len(right))):
        y = 20 + i * 8
        pdf.set_xy(12, y)
        pdf.set_font("Helvetica", "B" if i < len(left) and left[i].isupper() else "", 10)
        if i < len(left):
            pdf.cell(55, 6, left[i])
        pdf.set_xy(80, y)
        pdf.set_font("Helvetica", "B" if i < len(right) and right[i].isupper() else "", 10)
        if i < len(right):
            pdf.cell(120, 6, right[i])
    return bytes(pdf.output())


def _png(width: int = 40, height: int = 12) -> bytes:
    """A plain grey PNG, standing in for a screenshot."""
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    rows = b"".join(b"\x00" + b"\x88" * width for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


CONTACT_BOX = (
    f"<w:p {nsdecls('w')} xmlns:v='urn:schemas-microsoft-com:vml'>"
    "<w:r><w:pict><v:shape style='width:200pt;height:60pt'><v:textbox><w:txbxContent>"
    "<w:p><w:r><w:rPr><w:sz w:val='56'/></w:rPr><w:t>Riley Park</w:t></w:r></w:p>"
    "<w:p><w:r><w:rPr><w:sz w:val='14'/></w:rPr><w:t>Denver, CO</w:t></w:r></w:p>"
    "<w:p><w:r><w:rPr><w:sz w:val='14'/></w:rPr><w:t>T (303) 555 - 0199</w:t></w:r></w:p>"
    "<w:p><w:r><w:rPr><w:sz w:val='14'/></w:rPr><w:t>riley.park@example.com</w:t></w:r></w:p>"
    "</w:txbxContent></v:textbox></v:shape></w:pict></w:r></w:p>"
)


def consultant_docx() -> bytes:
    """A contractor's resume: agency and client engagements, workstreams and a screenshot.

    Riley Park is fictional. Planted: a confidentiality marking in the page header,
    contact details in a text box, a summary under an Experience heading, a figure
    that differs between Highlights and the role, undated client engagements, a
    present-tense line in a past engagement, a full-width image, small type and
    misspelled skills.
    """
    doc = Document()
    styles: Any = doc.styles
    styles["Normal"].font.name = "Helvetica"
    styles["Normal"].font.size = Pt(9)
    doc.sections[0].header.paragraphs[0].text = "•• CONFIDENTIAL – Internal Use"

    doc.add_paragraph().add_run("Experience").bold = True
    doc.element.body.insert(len(doc.element.body) - 1, parse_xml(CONTACT_BOX))
    doc.add_paragraph(
        "Analytics consultant who turns messy operational data into pricing and "
        "forecasting decisions for health and finance clients."
    )
    doc.add_paragraph().add_run("Highlights").bold = True
    doc.add_paragraph("Cut patient no-shows ~30% at Northwind Health with a reminder model.")

    doc.add_paragraph().add_run("Experience").bold = True
    doc.add_paragraph("Senior Analyst, Fabrikam Inc. - July 2023 – Present", style="Heading 2")
    doc.add_paragraph().add_run("Pricing").bold = True
    doc.add_paragraph("Rebuilt the discount model, lifting margin 4 points.", style="List Bullet")
    doc.add_paragraph("Set up weekly price tests across 120 stores.", style="List Bullet")
    doc.add_paragraph().add_run("Forecasting").bold = True
    doc.add_paragraph("Built a demand forecast used by 40 planners.", style="List Bullet")
    doc.add_picture(io.BytesIO(_png()), width=Pt(6.5 * 72), height=Pt(2 * 72))

    doc.add_paragraph("Consultant, Contoso Staffing - January 2019 – June 2023", style="Heading 2")
    doc.add_paragraph("Data Scientist, Northwind Health", style="Heading 2")
    doc.add_paragraph(
        "Built a reminder model that cut patient no-shows 25% across 14 clinics.  Led the "
        "rollout with clinic managers and trained 30 front-desk staff."
    )
    doc.add_paragraph("Analytics Lead, Tailspin Bank", style="Heading 2")
    doc.add_paragraph(
        "Provide weekly risk dashboards to the credit committee, covering 2 portfolios "
        "worth $1.2B in loans."
    )

    doc.add_paragraph().add_run("Skills").bold = True
    doc.add_paragraph("Python, SQL, AWS Sagemaker, Tableu, Milvius")

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def promotions_text() -> str:
    """Three titles held at one employer, listed under a single employer line with the
    whole tenure beside it, then an agency job with client engagements. The rule-based
    parser reads the employer line as a role of its own; Claude shouldn't."""
    return "\n".join(
        [
            "Avery Quinn",
            "Chicago, IL | avery.quinn@example.com | 312-555-0142",
            "",
            "EXPERIENCE",
            "",
            "Northwind Logistics, Chicago, IL\tMar 2014 – Present",
            "Director, Supply Chain Operations (Jan 2021 – Present)",
            "• Led a 40-person team across three distribution centers, cutting late "
            "shipments by 22%.",
            "• Built the first network-wide demand forecast, saving $3.1M in carrying costs.",
            "Senior Manager, Operations (Jun 2017 – Dec 2020)",
            "• Rolled out warehouse software to 6 sites in 9 months.",
            "Operations Analyst (Mar 2014 – May 2017)",
            "• Automated weekly inventory reporting, saving 10 hours a week.",
            "",
            "Brightline Partners, Milwaukee, WI\tJun 2010 – Feb 2014",
            "Consultant",
            "Fabrikam Foods",
            "• Mapped inbound freight for 120 suppliers.",
            "",
            "EDUCATION",
            "University of Wisconsin–Madison, B.S. Industrial Engineering, 2010",
        ]
    )


def stint_text() -> str:
    """One employer with a line describing it and three titles that share its tenure
    (no dates of their own), a page number left in the text, an activity section and a
    references line. Made up."""
    return "\n".join(
        [
            "Jordan Lee",
            "Denver, CO | jordan.lee@example.com | 720-555-0199",
            "PROFESSIONAL EXPERIENCE",
            "Contoso Health, Denver, CO\t2015 – 2023",
            "A regional hospital network with 12 sites and 9,000 staff.",
            "Director of Patient Access",
            "• Cut average ER wait times by 18% across 4 sites.",
            "Manager, Scheduling",
            "• Rebuilt the scheduling team and hired 14 coordinators.",
            "Supervisor, Registration",
            "• Trained 30 registrars on the new intake system.",
            "Fabrikam Clinics, Boulder, CO\t2012 – 2015",
            "Office Manager",
            "• Ran billing for 3 clinics, collecting $2.4M a year.",
            "Page 2",
            "EDUCATION",
            "University of Colorado, B.A. Psychology, 2012",
            "SPEAKING",
            "Speaker, Colorado Healthcare Access Summit, 2022",
            "References available upon request",
        ]
    )
