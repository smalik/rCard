"""Finds and parses date ranges written in the many ways resumes write them."""

import re

from plytos_api.imports.model import DateRange, YearMonth

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}  # fmt: skip
_SEASONS = {"spring": 3, "summer": 6, "fall": 9, "autumn": 9, "winter": 12}
_CURRENT = r"present|current|now|today|to\s+date|ongoing"

_MONTH_NAME = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
)
_SEASON = r"(?:spring|summer|fall|autumn|winter)"
_YEAR = r"(?:19|20)\d{2}"
_SHORT_YEAR = r"[’']\d{2}"

_POINT = (
    rf"(?:{_MONTH_NAME}\s*,?\s*(?:{_YEAR}|{_SHORT_YEAR})"
    rf"|{_SEASON}\s+{_YEAR}"
    rf"|(?:0?[1-9]|1[0-2])\s*[/.\-]\s*{_YEAR}"
    rf"|{_YEAR}\s*[/.\-]\s*(?:0?[1-9]|1[0-2])(?!\d)"
    rf"|{_YEAR})"
)
_SEP = r"\s*(?P<sep>–|—|-|−|to|through|thru|until)\s*"
_RANGE = re.compile(
    rf"(?P<start>{_POINT}){_SEP}(?P<end>{_POINT}|{_CURRENT})(?![\d/])",
    re.IGNORECASE,
)
_SINGLE = re.compile(rf"(?<![\d/])(?P<start>{_POINT})(?![\d/])", re.IGNORECASE)


def _point(text: str) -> tuple[YearMonth, str]:
    t = text.strip().lower().replace(",", " ")
    t = re.sub(r"\s+", " ", t)
    m = re.fullmatch(r"([a-z]+)\.?\s*((?:19|20)\d{2}|[’']\d{2})", t)
    if m and m.group(1) in _MONTHS:
        word, year_text = m.group(1), m.group(2)
        year = int(year_text) if len(year_text) == 4 else 2000 + int(year_text[1:])
        if year_text[0] in "’'" and year > 2040:
            year -= 100
        label = "Month YYYY" if len(word) > 3 and word not in ("sept",) else "Mon YYYY"
        if word == "may":
            label = "Month YYYY"
        if year_text[0] in "’'":
            label = "Mon 'YY"
        if text.strip().split()[0].endswith("."):
            label = "Mon. YYYY"
        return YearMonth(year=year, month=_MONTHS[word]), label
    if m and m.group(1) in _SEASONS:
        return YearMonth(year=int(m.group(2)), month=_SEASONS[m.group(1)]), "Season YYYY"
    m = re.fullmatch(r"(\d{1,2})\s*([/.\-])\s*(\d{4})", t)
    if m:
        label = ("MM" if len(m.group(1)) == 2 else "M") + m.group(2) + "YYYY"
        return YearMonth(year=int(m.group(3)), month=int(m.group(1))), label
    m = re.fullmatch(r"(\d{4})\s*([/.\-])\s*(\d{1,2})", t)
    if m:
        return YearMonth(year=int(m.group(1)), month=int(m.group(3))), "YYYY" + m.group(2) + "MM"
    return YearMonth(year=int(t[:4])), "YYYY"


def find_range(text: str) -> DateRange | None:
    """Returns the last date range in a line, or a single date if there is no range."""
    matches = list(_RANGE.finditer(text))
    if matches:
        m = matches[-1]
        start, start_format = _point(m.group("start"))
        end_text = m.group("end")
        if re.fullmatch(_CURRENT, end_text.strip(), re.IGNORECASE):
            return DateRange(
                raw=m.group(0).strip(),
                start=start,
                end=None,
                current=True,
                start_format=start_format,
                end_format=None,
                separator=m.group("sep").lower(),
                current_word=end_text.strip(),
            )
        end, end_format = _point(end_text)
        return DateRange(
            raw=m.group(0).strip(),
            start=start,
            end=end,
            current=False,
            start_format=start_format,
            end_format=end_format,
            separator=m.group("sep").lower(),
        )
    singles = list(_SINGLE.finditer(text))
    if singles:
        m = singles[-1]
        point, label = _point(m.group("start"))
        return DateRange(
            raw=m.group(0).strip(),
            start=point,
            end=point,
            current=False,
            start_format=label,
            end_format=label,
            separator=None,
        )
    return None


def only_dates(text: str) -> bool:
    """Whether the text is nothing but dates: a range, or a date on its own."""
    rest = _SINGLE.sub(" ", _RANGE.sub(" ", text))
    return bool(text.strip()) and re.search(r"[^\W_]", rest) is None


def strip_range(text: str, found: DateRange) -> str:
    """The line with its date range removed, tidied of leftover separators."""
    rest = text.replace(found.raw, " ")
    rest = re.sub(r"[\s|,;:–—\-]+$", "", rest)
    rest = re.sub(r"^[\s|,;:–—\-]+", "", rest)
    rest = re.sub(r"\(\s*\)", "", rest)
    return re.sub(r"\s{2,}", " ", rest).strip()
