"""Careers with every fact known, to score readings against.

The made-up ones here are written out as resumes (layouts.py). Everyone in them is
fictional; employers are the usual stand-in names. The same models hold the labels
written by hand for real resumes, which never leave the machine they're made on: a
real resume may leave things out, so most fields can be empty.
"""

# The accomplishments are written whole, the way a resume has them.
# ruff: noqa: E501

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PRESENT = "present"


class Group(BaseModel):
    """Accomplishments under one title, with the workstream label they sit under, if any."""

    label: str | None = None
    items: list[str]


class Position(BaseModel):
    title: str
    # YYYY-MM, or YYYY when only the year is written; end may be "present".
    start: str | None = None
    end: str | None = None
    # The client, for consulting work shown under the consultancy.
    client: str | None = None
    groups: list[Group] = Field(default_factory=list)

    @property
    def items(self) -> list[str]:
        return [item for group in self.groups for item in group.items]


class Employment(BaseModel):
    employer: str
    location: str | None = None
    volunteer: bool = False
    # Newest title first, as resumes list them.
    positions: list[Position]

    @property
    def start(self) -> str | None:
        return min((p.start for p in self.positions if p.start), default=None)

    @property
    def end(self) -> str | None:
        ends = [p.end for p in self.positions if p.end]
        return PRESENT if PRESENT in ends else max(ends, default=None)


class Highlight(BaseModel):
    text: str
    # The employer the highlight names, when it names one.
    names: str | None = None


class SkillGroup(BaseModel):
    category: str
    items: list[str]


class School(BaseModel):
    school: str
    degree: str = ""
    field: str = ""
    year: str | None = None


class Award(BaseModel):
    name: str
    issuer: str | None = None
    year: str | None = None


class Talk(BaseModel):
    year: str
    text: str


class Other(BaseModel):
    """Anything else with a card of its own: a credential, a project, an activity."""

    kind: Literal["credential", "project", "activity"]
    text: str
    year: str | None = None


class Career(BaseModel):
    key: str
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    summary: str | None = None
    highlights: list[Highlight] = Field(default_factory=list)
    # Newest first.
    employments: list[Employment] = Field(default_factory=list)
    skills: list[SkillGroup] = Field(default_factory=list)
    education: list[School] = Field(default_factory=list)
    awards: list[Award] = Field(default_factory=list)
    talks: list[Talk] = Field(default_factory=list)
    other: list[Other] = Field(default_factory=list)
    # A label for a real resume: the file it describes, and where the right answer
    # was a judgment call.
    source: str | None = None
    notes: str | None = None
    # When every employer is written as a stand-in ("Company Name"), which jobs were
    # at the same employer can't be known: titles are then scored without them.
    anonymous_employers: bool = False
    # What the label leaves out: cards of these kinds, and cards holding these words,
    # are neither scored nor counted as invented.
    unscored_kinds: list[str] = Field(default_factory=list)
    unscored: list[str] = Field(default_factory=list)


MORGAN = Career(
    key="morgan",
    name="Morgan Ellis",
    email="morgan.ellis@example.com",
    phone="(312) 555-0148",
    location="Chicago, IL",
    summary=(
        "Operations leader who builds regional distribution networks that ship on time "
        "and cost less to run."
    ),
    highlights=[
        Highlight(text="Cut delivery cost per order by 14% across nine warehouses."),
        Highlight(
            text="Named to the Tailspin Freight leadership bench after two years.",
            names="Tailspin Freight",
        ),
    ],
    employments=[
        Employment(
            employer="Northwind Logistics",
            location="Chicago, IL",
            positions=[
                Position(
                    title="Director of Operations",
                    start="2021-04",
                    end=PRESENT,
                    groups=[
                        Group(
                            label="Network redesign",
                            items=[
                                "Moved 40% of volume to two new cross-docks within one year.",
                                "Renegotiated linehaul contracts worth $18M a year.",
                            ],
                        ),
                        Group(
                            label="People",
                            items=[
                                "Grew the site leadership team from 6 to 11 managers.",
                                "Started a rotation that promoted 9 supervisors from the floor.",
                            ],
                        ),
                    ],
                ),
                Position(
                    title="Senior Operations Manager",
                    start="2018-02",
                    end="2021-03",
                    groups=[
                        Group(
                            items=[
                                "Ran three warehouses with 420 staff across two shifts.",
                                "Raised on-time shipping from 91% to 98.5% in 18 months.",
                                "Rolled out a new warehouse management system without a lost day.",
                            ]
                        )
                    ],
                ),
            ],
        ),
        Employment(
            employer="Tailspin Freight",
            location="Milwaukee, WI",
            positions=[
                Position(
                    title="Operations Manager",
                    start="2014-06",
                    end="2018-01",
                    groups=[
                        Group(
                            items=[
                                "Opened the Kenosha hub on schedule and $1.2M under budget.",
                                "Cut overtime by 22% with a demand-based shift plan.",
                                "Led safety audits that took recordable injuries to zero for a year.",
                            ]
                        )
                    ],
                )
            ],
        ),
        Employment(
            employer="Contoso Retail",
            location="Chicago, IL",
            positions=[
                Position(
                    title="Operations Analyst",
                    start="2011-07",
                    end="2014-05",
                    groups=[
                        Group(
                            items=[
                                "Built the weekly labor model used by 60 stores.",
                                "Found $700K a year in freight billing errors.",
                            ]
                        )
                    ],
                )
            ],
        ),
    ],
    skills=[
        SkillGroup(category="Operations", items=["Lean", "Six Sigma", "S&OP", "Network design"]),
        SkillGroup(category="Tools", items=["SQL", "Tableau", "Excel", "SAP"]),
    ],
    education=[
        School(
            school="University of Illinois",
            degree="B.S.",
            field="Industrial Engineering",
            year="2011",
        )
    ],
    awards=[
        Award(name="President's Award for Operations", issuer="Northwind Logistics", year="2022")
    ],
    talks=[
        Talk(year="2023", text="Speaker, Midwest Supply Chain Forum: Designing resilient networks"),
        Talk(year="2021", text="Panelist, Great Lakes Logistics Summit: Hiring in a tight market"),
    ],
)

SAM = Career(
    key="sam",
    name="Sam Okafor",
    email="sam.okafor@example.com",
    phone="(512) 555-0110",
    location="Austin, TX",
    summary="Data engineer who turns messy event streams into data people trust.",
    highlights=[Highlight(text="Built pipelines that now move 2 billion events a day.")],
    employments=[
        Employment(
            employer="Litware Inc.",
            location="Austin, TX",
            positions=[
                Position(
                    title="Senior Data Engineer",
                    start="2022-02",
                    end=PRESENT,
                    groups=[
                        Group(
                            items=[
                                "Replaced nightly batch jobs with streaming that lands data in minutes.",
                                "Cut the warehouse bill by 31% by pruning unused tables.",
                                "Set up data contracts for 14 producer teams.",
                                "Mentored four engineers who were each promoted within a year.",
                            ]
                        )
                    ],
                )
            ],
        ),
        Employment(
            employer="Proseware",
            location="Remote",
            positions=[
                Position(
                    title="Data Engineer",
                    start="2019-07",
                    end="2022-01",
                    groups=[
                        Group(
                            items=[
                                "Moved 300 reports from spreadsheets to a governed dashboard.",
                                "Wrote the test suite that caught bad loads before morning reports.",
                                "Built the customer churn feature store used by three models.",
                            ]
                        )
                    ],
                )
            ],
        ),
        Employment(
            employer="Fabrikam Analytics",
            location="Dallas, TX",
            positions=[
                Position(
                    title="Data Analyst",
                    start="2017-06",
                    end="2019-06",
                    groups=[
                        Group(
                            items=[
                                "Automated the monthly board pack and saved two days a month.",
                                "Cleaned 12 years of sales history for the pricing project.",
                            ]
                        )
                    ],
                )
            ],
        ),
    ],
    skills=[
        SkillGroup(category="Languages", items=["Python", "SQL", "Scala"]),
        SkillGroup(category="Platforms", items=["Spark", "Kafka", "dbt", "Snowflake"]),
    ],
    education=[
        School(
            school="Texas State University",
            degree="B.S.",
            field="Computer Science",
            year="2017",
        )
    ],
    awards=[],
    talks=[],
)

CAREERS: list[Career] = [MORGAN, SAM]
