import re
from datetime import datetime

# Formato típico do zabbix_server.log:
#  1376:20241127:153045.123 Starting Zabbix Server (7.0.0)
ZBX_SERVER_REGEX = re.compile(
    r"^\s*(?P<pid>\d+):(?P<date>\d{8}):(?P<time>\d{6})(?:\.\d+)?:\s*(?P<msg>.*)$"
)


def guess_level(msg: str) -> str:
    up = msg.upper()
    if "FATAL" in up or "CRITICAL" in up:
        return "CRITICAL"
    if "ERROR" in up or "FAILED" in up or "UNABLE" in up:
        return "ERROR"
    if "WARN" in up or "WARNING" in up:
        return "WARN"
    if "DEBUG" in up:
        return "DEBUG"
    return "INFO"


def parse_zabbix_server_line(line: str, host: str = "zabbix-server"):
    line = line.rstrip("\n")
    m = ZBX_SERVER_REGEX.match(line)

    if m:
        raw_date = m.group("date")
        raw_time = m.group("time")
        msg = m.group("msg").strip()

        year = int(raw_date[0:4])
        month = int(raw_date[4:6])
        day = int(raw_date[6:8])

        hour = int(raw_time[0:2])
        minute = int(raw_time[2:4])
        second = int(raw_time[4:6])

        dt = datetime(year, month, day, hour, minute, second)
        level = guess_level(msg)
        source = "zabbix_server"
    else:
        # fallback: formato diferente, mas não joga fora
        dt = datetime.now()
        msg = line.strip()
        level = guess_level(msg)
        source = "zabbix_server_raw"

    return {
        "timestamp": dt.isoformat(sep=" "),
        "source": source,
        "level": level,
        "host": host,
        "message": msg,
    }
