from pathlib import Path
from .models import init_db, insert_log
from .parser_linux import parse_syslog_line
from .parser_zabbix_server import parse_zabbix_server_line


def ingest_syslog(path: str):
    """
    Lê um arquivo de syslog e grava na tabela logs.
    """
    init_db()
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {p}")

    count = 0
    with p.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.rstrip("\n")
            parsed = parse_syslog_line(line)
            if not parsed:
                continue
            insert_log(
                parsed["timestamp"],
                parsed["source"],
                parsed["level"],
                parsed["host"],
                parsed["message"],
            )
            count += 1
    return count


def ingest_zabbix_server(path: str, host: str = "zabbix-server"):
    """
    Lê um zabbix_server.log e grava na tabela logs.
    """
    init_db()
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {p}")

    count = 0
    with p.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.rstrip("\n")
            parsed = parse_zabbix_server_line(line, host=host)
            if not parsed:
                continue
            insert_log(
                parsed["timestamp"],
                parsed["source"],
                parsed["level"],
                parsed["host"],
                parsed["message"],
            )
            count += 1
    return count

