# src/cli.py
from __future__ import annotations

import argparse
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

import paramiko

from .analyzer import (
    get_connection,
    print_table,
    last_logs,
    count_by_level,
    filter_logs,
    filter_hosts,
    top_errors,
)

# ---------------------------------------------------------------------------
# Ingestão de logs
# ---------------------------------------------------------------------------


def _insert_log(
    conn,
    *,
    timestamp: str,
    source: str,
    level: str,
    host: str,
    message: str,
) -> None:
    conn.execute(
        """
        INSERT INTO logs (timestamp, source, level, host, message)
        VALUES (?, ?, ?, ?, ?)
        """,
        (timestamp, source, level, host, message),
    )


def _guess_level_from_line(line: str) -> str:
    upper = line.upper()
    if " CRITICAL " in upper:
        return "CRITICAL"
    if " ERROR " in upper:
        return "ERROR"
    return "INFO"


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ingest_syslog_file(path: str, default_host: str = "localhost") -> int:
    """
    Ingestão bem simples de um arquivo de syslog.
    Cada linha vira uma entrada de nível INFO no source 'syslog'.
    """
    path_obj = Path(path)
    if not path_obj.is_file():
        raise FileNotFoundError(path)

    count = 0
    with get_connection() as conn, path_obj.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            timestamp = _now_str()
            _insert_log(
                conn,
                timestamp=timestamp,
                source="syslog",
                level="INFO",
                host=default_host,
                message=line,
            )
            count += 1
        conn.commit()
    return count


def ingest_zabbix_server_log(path: str, host_alias: str) -> int:
    """
    Ingestão simplificada de zabbix_server.log.
    Não tenta ser perfeito, só classifica INFO/ERROR/CRITICAL por substring
    e grava a linha inteira como mensagem.
    """
    path_obj = Path(path)
    if not path_obj.is_file():
        raise FileNotFoundError(path)

    count = 0
    with get_connection() as conn, path_obj.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue

            level = _guess_level_from_line(line)
            # timestamp “fake” atual, porque o formato do arquivo é chato;
            # para uso de análise já resolve.
            timestamp = _now_str()

            _insert_log(
                conn,
                timestamp=timestamp,
                source="zabbix_server_raw",
                level=level,
                host=host_alias,
                message=line,
            )
            count += 1
        conn.commit()
    return count


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------


def cmd_init_db(args: argparse.Namespace) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS logs (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                source    TEXT NOT NULL,
                level     TEXT NOT NULL,
                host      TEXT NOT NULL,
                message   TEXT NOT NULL
            )
            """
        )
        conn.commit()
    print("Banco inicializado!")


def cmd_ingest_syslog(args: argparse.Namespace) -> None:
    count = ingest_syslog_file(args.path)
    print(f"Ingeridas {count} linhas de syslog.")


def cmd_remote_zbx_server(args: argparse.Namespace) -> None:
    host = args.host
    user = args.user
    password = args.password
    remote_path = args.remote_path
    alias = args.alias or host

    print(f"[DEBUG] Conectando em {host} via SSH como {user}...")
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        local_tmp = tmp.name

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=host, username=user, password=password)

        sftp = client.open_sftp()
        print(
            f"[DEBUG] Baixando {remote_path} -> {local_tmp} ..."
        )
        sftp.get(remote_path, local_tmp)
        sftp.close()
        client.close()

        size = os.path.getsize(local_tmp)
        print(f"[DEBUG] Download concluído. Tamanho: {size} bytes")

        print(
            f"[DEBUG] Ingerindo {local_tmp} como host={alias} ..."
        )
        count = ingest_zabbix_server_log(local_tmp, alias)
        print(f"Ingest finalizada: {count} linhas.")
    finally:
        try:
            os.unlink(local_tmp)
        except OSError:
            pass


def cmd_last(args: argparse.Namespace) -> None:
    rows = last_logs(limit=args.limit)

    print_table(
        "Últimos logs",
        [
            (r["timestamp"], r["source"], r["level"], r["host"], r["message"])
            for r in rows
        ],
        ["Timestamp", "Source", "Level", "Host", "Message"],
    )


def cmd_stats(args: argparse.Namespace) -> None:
    rows = count_by_level()
    print_table(
        "Quantidade por nível",
        rows,
        ["Level", "Count"],
    )


# ---------------------------------------------------------------------------
# Presets do filtro
# ---------------------------------------------------------------------------
PRESETS: Dict[str, Dict[str, Any]] = {
    "email": {
        "level": "ERROR",
        "contains": "failed to send email",
    },
    "network": {
        "contains": "network",
    },
    "proxy": {
        "contains": "proxy",
    },
    "agent": {
        "contains": "Zabbix agent",
    },
    "db": {
        "contains": "database",
    },
}


def _apply_preset(args: argparse.Namespace) -> argparse.Namespace:
    """
    Aplica preset se informado.
    CLI SEMPRE tem prioridade: só preenche o que estiver None.
    """
    if not args.preset:
        return args

    preset = PRESETS.get(args.preset, {})
    # level
    if getattr(args, "level", None) is None and "level" in preset:
        args.level = preset["level"]
    # contains
    if getattr(args, "contains", None) is None and "contains" in preset:
        args.contains = preset["contains"]
    # host/source/since/until podem ter presets no futuro
    return args


def cmd_filter(args: argparse.Namespace) -> None:
    args = _apply_preset(args)

    if args.distinct_hosts:
        hosts = filter_hosts(
            level=args.level,
            contains=args.contains,
            host=args.host,
            source=args.source,
            since=args.since,
            until=args.until,
            limit=args.limit,
        )
        print_table(
            "Hosts distintos",
            hosts,
            ["Host", "Count"],
        )
        return

    rows = filter_logs(
        level=args.level,
        contains=args.contains,
        host=args.host,
        source=args.source,
        since=args.since,
        until=args.until,
        asc=args.asc,
        limit=args.limit,
    )

    print_table(
        "Resultados do filtro",
        [
            (r["timestamp"], r["source"], r["level"], r["host"], r["message"])
            for r in rows
        ],
        ["Timestamp", "Source", "Level", "Host", "Message"],
    )


def cmd_top_errors(args: argparse.Namespace) -> None:
    args = _apply_preset(args)

    rows = top_errors(
        level=args.level,
        contains=args.contains,
        host=args.host,
        source=args.source,
        since=args.since,
        until=args.until,
        limit=args.limit,
    )

    print_table(
        f"Top mensagens (level={args.level})",
        rows,
        ["Count", "Message"],
    )


# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="magiclog",
        description="Ferramenta de análise de logs (syslog + Zabbix Server)",
    )

    sub = parser.add_subparsers(dest="cmd")

    # init-db
    p_init = sub.add_parser("init-db", help="Inicializar banco de dados")
    p_init.set_defaults(func=cmd_init_db)

    # ingest-syslog
    p_ing = sub.add_parser("ingest-syslog", help="Ingerir arquivo syslog local")
    p_ing.add_argument("path", help="Caminho do arquivo syslog (ex: /var/log/syslog)")
    p_ing.set_defaults(func=cmd_ingest_syslog)

    # remote-zbx-server
    p_remote = sub.add_parser(
        "remote-zbx-server", help="Baixar e ingerir zabbix_server.log via SSH"
    )
    p_remote.add_argument("host", help="Endereço/IP do servidor Zabbix")
    p_remote.add_argument("user", help="Usuário SSH")
    p_remote.add_argument("password", help="Senha SSH")
    p_remote.add_argument(
        "remote_path",
        help="Caminho do log remoto (ex: /var/log/zabbix/zabbix_server.log)",
    )
    p_remote.add_argument(
        "--alias",
        help="Nome para identificar esse host nos logs (ex: srvzbx)",
    )
    p_remote.set_defaults(func=cmd_remote_zbx_server)

    # last
    p_last = sub.add_parser("last", help="Mostrar últimos logs")
    p_last.add_argument(
        "-n",
        "--limit",
        type=int,
        default=20,
        help="Quantidade de linhas (default: 20)",
    )
    p_last.set_defaults(func=cmd_last)

    # stats
    p_stats = sub.add_parser("stats", help="Estatísticas por nível")
    p_stats.set_defaults(func=cmd_stats)

    # filter
    p_filter = sub.add_parser("filter", help="Filtrar logs com critérios")
    p_filter.add_argument(
        "--distinct-hosts",
        action="store_true",
        help="Listar somente hosts distintos que possuem logs correspondentes",
    )
    p_filter.add_argument(
        "-l",
        "--level",
        choices=["INFO", "ERROR", "CRITICAL"],
        help="Nível do log (INFO, ERROR, CRITICAL)",
    )
    p_filter.add_argument(
        "-c",
        "--contains",
        help="Texto que a mensagem deve conter",
    )
    p_filter.add_argument(
        "--host",
        help="Filtrar por host",
    )
    p_filter.add_argument(
        "--source",
        help="Filtrar por fonte (ex: zabbix_server_raw)",
    )
    p_filter.add_argument(
        "--since",
        help='A partir de (ex: "2025-11-27 21:00")',
    )
    p_filter.add_argument(
        "--until",
        help='Até (ex: "2025-11-27 22:00")',
    )
    p_filter.add_argument(
        "-n",
        "--limit",
        type=int,
        default=20,
        help="Quantidade máxima de linhas (default: 20)",
    )
    p_filter.add_argument(
        "--asc",
        action="store_true",
        help="Ordem cronológica (mais antigos primeiro)",
    )
    p_filter.add_argument(
        "--preset",
        choices=["email", "network", "proxy", "agent", "db"],
        help="Usar filtro pronto (ex: --preset email)",
    )
    p_filter.set_defaults(func=cmd_filter)

    # top-errors
    p_top = sub.add_parser(
        "top-errors",
        help="Listar mensagens mais frequentes (por default: ERROR)",
    )
    p_top.add_argument(
        "-l",
        "--level",
        choices=["INFO", "ERROR", "CRITICAL"],
        default="ERROR",
        help="Nível do log (default: ERROR)",
    )
    p_top.add_argument(
        "-c",
        "--contains",
        help="Texto que a mensagem deve conter",
    )
    p_top.add_argument(
        "--host",
        help="Filtrar por host",
    )
    p_top.add_argument(
        "--source",
        help="Filtrar por fonte (ex: zabbix_server_raw)",
    )
    p_top.add_argument(
        "--since",
        help='A partir de (ex: "2025-11-27 21:00")',
    )
    p_top.add_argument(
        "--until",
        help='Até (ex: "2025-11-27 22:00")',
    )
    p_top.add_argument(
        "-n",
        "--limit",
        type=int,
        default=20,
        help="Quantidade de mensagens agregadas (default: 20)",
    )
    p_top.add_argument(
        "--preset",
        choices=["email", "network", "proxy", "agent", "db"],
        help="Usar preset pronto (ex: --preset email)",
    )
    p_top.set_defaults(func=cmd_top_errors)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
