# src/analyzer.py
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, List, Dict, Any, Tuple, Optional

from rich.console import Console
from rich.table import Table

DB_PATH = Path("data") / "logs.db"
console = Console()


# ---------------------------------------------------------------------------
# Conexão com o banco
# ---------------------------------------------------------------------------
def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Impressão de tabelas
# ---------------------------------------------------------------------------
def print_table(title: str, rows: Iterable[Iterable[Any]], columns: List[str]) -> None:
    """
    Pequeno helper para imprimir tabelas com Rich.

    :param title: título da tabela
    :param rows:  lista de linhas (iteráveis)
    :param columns: nomes das colunas (headers)
    """
    table = Table(title=title, show_lines=True)
    for col in columns:
        table.add_column(str(col))

    for row in rows:
        table.add_row(*[str(col) for col in row])

    console.print(table)


# ---------------------------------------------------------------------------
# Consultas básicas
# ---------------------------------------------------------------------------
def last_logs(limit: int = 20) -> List[Dict[str, Any]]:
    """
    Retorna os últimos N logs cadastrados.
    """
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT timestamp, source, level, host, message
            FROM logs
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def count_by_level() -> List[Tuple[str, int]]:
    """
    Conta quantos logs existem por nível.
    """
    with get_connection() as conn:
        cur = conn.execute(
            """
            SELECT level, COUNT(*) AS count
            FROM logs
            GROUP BY level
            ORDER BY count DESC
            """
        )
        return [(row["level"], row["count"]) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Filtro genérico
# ---------------------------------------------------------------------------
def _build_where(
    level: Optional[str] = None,
    contains: Optional[str] = None,
    host: Optional[str] = None,
    source: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> Tuple[str, list]:
    where = ["1=1"]
    params: list[Any] = []

    if level:
        where.append("level = ?")
        params.append(level)

    if contains:
        where.append("message LIKE ?")
        params.append(f"%{contains}%")

    if host:
        where.append("host = ?")
        params.append(host)

    if source:
        where.append("source = ?")
        params.append(source)

    if since:
        where.append("timestamp >= ?")
        params.append(since)

    if until:
        where.append("timestamp <= ?")
        params.append(until)

    return " AND ".join(where), params


def filter_logs(
    *,
    level: Optional[str] = None,
    contains: Optional[str] = None,
    host: Optional[str] = None,
    source: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    asc: bool = False,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Retorna logs filtrados pelos critérios fornecidos.
    """
    where, params = _build_where(level, contains, host, source, since, until)

    order = "ASC" if asc else "DESC"

    query = f"""
        SELECT timestamp, source, level, host, message
        FROM logs
        WHERE {where}
        ORDER BY timestamp {order}
        LIMIT ?
    """
    params.append(limit)

    with get_connection() as conn:
        cur = conn.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def filter_hosts(
    *,
    level: Optional[str] = None,
    contains: Optional[str] = None,
    host: Optional[str] = None,
    source: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 20,
) -> List[Tuple[str, int]]:
    """
    Versão especial do filtro: retorna apenas hosts distintos + quantidade de logs.
    Usado para o modo --distinct-hosts.
    """
    where, params = _build_where(level, contains, host, source, since, until)

    query = f"""
        SELECT host, COUNT(*) AS count
        FROM logs
        WHERE {where}
        GROUP BY host
        ORDER BY count DESC
        LIMIT ?
    """
    params.append(limit)

    with get_connection() as conn:
        cur = conn.execute(query, params)
        return [(row["host"], row["count"]) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Top erros (agrupado por mensagem)
# ---------------------------------------------------------------------------
def top_errors(
    *,
    level: str = "ERROR",
    contains: Optional[str] = None,
    host: Optional[str] = None,
    source: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = 20,
) -> List[Tuple[int, str]]:
    """
    Retorna as mensagens mais frequentes, obedecendo aos filtros.
    """
    where, params = _build_where(level, contains, host, source, since, until)

    query = f"""
        SELECT COUNT(*) AS count, message
        FROM logs
        WHERE {where}
        GROUP BY message
        ORDER BY count DESC
        LIMIT ?
    """
    params.append(limit)

    with get_connection() as conn:
        cur = conn.execute(query, params)
        return [(row["count"], row["message"]) for row in cur.fetchall()]
