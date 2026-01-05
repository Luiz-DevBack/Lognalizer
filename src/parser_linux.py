import re
from datetime import datetime

SYSLOG_REGEX = re.compile(
    r"^(?P<month>\w{3})\s+(?P<day>\d{1,2})\s+(?P<time>\d{2}:\d{2}:\d{2})\s+(?P<host>[\w\.\-]+)\s+(?P<rest>.*)$"
)

MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
    "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
    "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def guess_level(msg: str) -> str:
    up = msg.upper()
    if "CRIT" in up or "FATAL" in up:
        return "CRITICAL"
    if "ERROR" in up or " ERR " in up:
        return "ERROR"
    if "WARN" in up:
        return "WARN"
    return "INFO"


def parse_syslog_line(line: str, year: int | None = None):
    m = SYSLOG_REGEX.match(line)
    if not m:
        return None

    now = datetime.now()
    year = year or now.year
    month = MONTHS.get(m.group("month"), now.month)
    day = int(m.group("day"))
    time_str = m.group("time")
    host = m.group("host")
    rest = m.group("rest").strip()

    dt = datetime.strptime(
        f"{year}-{month:02d}-{day:02d} {time_str}",
        "%Y-%m-%d %H:%M:%S",
    )

    return {
        "timestamp": dt.isoformat(sep=" "),
        "source": "syslog",
        "level": guess_level(rest),
        "host": host,
        "message": rest,
    }
