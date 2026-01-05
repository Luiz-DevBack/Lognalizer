import re
from datetime import datetime

# Exemplo comum de linha:
#  1376:20241127:153045.123 Starting Zabbix Proxy (7.0.0)
ZBX_PROXY_REGEX = re.compile(
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


def parse_zabbix_proxy_line(line: str, host: str = "zabbix-proxy"):
    """
    Tenta parsear o formato padrão do zabbix_proxy.log.
    Se não bater o regex, ainda assim retorna algo, usando now() como timestamp.
    """
    line = line.rstrip("\n")

    m = ZBX_PROXY_REGEX.match(line)
    if m:
        raw_date = m.group("date")  # YYYYMMDD
        raw_time = m.group("time")  # HHMMSS
        msg = m.group("msg").strip()

        year = int(raw_date[0:4])
        month = int(raw_date[4:6])
        day = int(raw_date[6:8])

        hour = int(raw_time[0:2])
        minute = int(raw_time[2:4])
        second = int(raw_time[4:6])

        dt = datetime(year, month, day, hour, minute, second)
        level = guess_level(msg)
        return {
            "timestamp": dt.isoformat(sep=" "),
            "source": "zabbix_proxy",
            "level": level,
            "host": host,
            "message": msg,
        }

    # fallback: não bateu o regex, mas não vamos perder a linha
    now = datetime.now()
    msg = line.strip()
    level = guess_level(msg)
    return {
        "timestamp": now.isoformat(sep=" "),
        "source": "zabbix_proxy_raw",
        "level": level,
        "host": host,
        "message": msg,
    }

