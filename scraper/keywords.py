"""Nurse-vacancy keyword matching and level classification."""
import re

# (pattern, level) — order matters: specific levels before the generic 護士
_PATTERNS: list = [
    (re.compile(r"註冊護士"), "RN"),
    (re.compile(r"登记护士"), "RN"),
    (re.compile(r"Registered\s*Nurse", re.I), "RN"),
    (re.compile(r"(?<![A-Za-z])RN(?![A-Za-z])"), "RN"),
    (re.compile(r"登記護士"), "EN"),
    (re.compile(r"登记护士"), "EN"),
    (re.compile(r"Enrolled\s*Nurse", re.I), "EN"),
    (re.compile(r"Nursing\s*Officer", re.I), "RN"),
    (re.compile(r"(?<![A-Za-z])EN(?![A-Za-z])"), "EN"),
    (re.compile(r"護士"), "護士"),
    (re.compile(r"护士"), "護士"),
    (re.compile(r"(?<![A-Za-z])Nurse(?![A-Za-z])", re.I), "護士"),
]


def classify(title: str | None) -> str | None:
    """Return 'RN' / 'EN' / '護士' if the title is a nurse vacancy, else None."""
    if not title:
        return None
    for pat, level in _PATTERNS:
        if pat.search(title):
            return level
    return None


def is_nurse(title: str | None) -> bool:
    return classify(title) is not None
