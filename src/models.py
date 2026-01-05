import sqlite3
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import re

# =====================================
# Configuração global
# =====================================

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "logs.db"


# =====================================
# Helpers genéricos
# =====================================

def datetime_utc_now() -> str:
    """
    Retorna datetime UTC em string padrão usada nos logs.
    """
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


# =====================================
# Conexão com o banco
# =====================================

def get_connection() -> sqlite3.Connection:
    """
    Abre conexão com SQLite. Row retorna dict-like.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# =====================================
# Inicialização da tabela
# =====================================

def init_db() -> None:
    """
    Cria a tabela de logs, caso ela não exista, e índices básicos.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            source TEXT,
            level TEXT,
            host TEXT,
            message TEXT,
            cause_group TEXT,
            cause_reason TEXT,
            cause_action TEXT
        )
    """)

    # Índices pra ficar mais suave quando o banco crescer
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_logs_level_ts
        ON logs(level, timestamp)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_logs_host_ts
        ON logs(host, timestamp)
    """)

    conn.commit()
    conn.close()


# =====================================
# Inserção de logs
# =====================================

def insert_log(
    timestamp: str,
    source: str,
    level: str,
    host: str,
    message: str,
    cause_group: Optional[str] = None,
    cause_reason: Optional[str] = None,
    cause_action: Optional[str] = None,
) -> None:
    """
    Insere uma linha na tabela logs.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO logs
        (timestamp, source, level, host, message, cause_group, cause_reason, cause_action)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (timestamp, source, level, host, message, cause_group, cause_reason, cause_action),
    )

    conn.commit()
    conn.close()


# =====================================
# Detecção: esse arquivo parece ser um LOG?
# =====================================

def is_probably_log(stream, filename: Optional[str] = None, max_bytes: int = 8192) -> bool:
    """
    Heurística simples pra decidir se um arquivo parece ser um log de texto.

    Critérios:
      - Não pode ser binário (muitos bytes estranhos).
      - Conteúdo em texto.
      - Várias linhas com cara de log: timestamps + palavras tipo ERROR/WARNING/INFO/Notice/Exception.
      - Reconhece formatos comuns, inclusive PHP error log:
        [22-Sep-2025 14:53:35 Europe/Berlin] PHP Notice: ...
    """
    pos_before = stream.tell()
    chunk = stream.read(max_bytes)
    stream.seek(pos_before)

    if not chunk:
        return False

    if isinstance(chunk, bytes):
        non_text = sum(1 for b in chunk if b in (0, 1, 2, 3, 4, 5, 6, 7, 8) or b > 126)
        ratio = non_text / len(chunk)
        if ratio > 0.15:
            return False
        text = chunk.decode("utf-8", errors="ignore")
    else:
        text = str(chunk)

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False

    php_ts_pattern = re.compile(
        r"^\[\d{2}-[A-Za-z]{3}-\d{4}\s+\d{2}:\d{2}:\d{2}\s+[^]]+\]"
    )
    iso_ts_pattern = re.compile(
        r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}"
    )
    syslog_ts_pattern = re.compile(
        r"^[A-Z][a-z]{2}\s+[ 0-9]{2}\s+\d{2}:\d{2}:\d{2}"
    )

    level_keywords = re.compile(
        r"\b(ERROR|WARN(ING)?|INFO|CRITICAL|NOTICE|EXCEPTION)\b",
        re.IGNORECASE,
    )

    scored_lines = 0
    for ln in lines[:20]:
        if len(ln) < 15:
            continue

        has_ts = (
            php_ts_pattern.search(ln)
            or iso_ts_pattern.search(ln)
            or syslog_ts_pattern.search(ln)
        )
        has_level = level_keywords.search(ln)

        if has_ts or has_level:
            scored_lines += 1

    total_considered = min(len(lines), 20)
    if scored_lines >= 2:
        return True
    if total_considered > 0 and scored_lines / total_considered >= 0.3:
        return True

    if filename:
        fname = filename.lower()
        if fname.endswith((".log", ".txt", ".out", ".err")) and scored_lines >= 1:
            return True

    return False


# =====================================
# Parser específico: PHP error log
# =====================================

_php_error_pattern = re.compile(
    r"""
    ^\[
        (?P<ts>\d{2}-[A-Za-z]{3}-\d{4}\s+\d{2}:\d{2}:\d{2})   # 02-Oct-2025 15:59:40
        \s+
        (?P<tz>[^\]]+)                                       # Europe/Berlin
    \]\s+
    PHP\s+
        (?P<php_level>Notice|Warning|Fatal\ error|Parse\ error|Deprecated|Error)
    :\s+
        (?P<rest>.*)
    """,
    re.VERBOSE | re.IGNORECASE,
)

def parse_php_error_line(line: str) -> Optional[Dict[str, str]]:
    """
    Tenta interpretar uma linha do php_errors.log.

    Exemplo:
      [02-Oct-2025 15:59:40 Europe/Berlin] PHP Notice: cURL error:
      Failed to connect to 192.168.0.204 port 8443: Connection refused in ...

    Retorna dict com:
      timestamp, level, message, cause_group, cause_reason, cause_action
    ou None se não bater com o padrão.
    """
    m = _php_error_pattern.match(line)
    if not m:
        return None

    ts_str = m.group("ts")
    php_level = m.group("php_level")
    rest = m.group("rest").strip()

    # converte timestamp para YYYY-MM-DD HH:MM:SS
    try:
        dt = datetime.strptime(ts_str, "%d-%b-%Y %H:%M:%S")
        timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        timestamp = datetime_utc_now()

    # mapeia nível PHP -> nível interno
    php_level_lower = php_level.lower()
    if "fatal" in php_level_lower or "error" in php_level_lower:
        level = "ERROR"
    elif "warning" in php_level_lower:
        level = "WARNING"
    elif "notice" in php_level_lower:
        level = "WARNING"
    else:
        level = "INFO"

    cause_group = None
    cause_reason = None
    cause_action = None

    # tenta extrair IP/porta se tiver cURL error
    ip = None
    port = None
    ip_port_match = re.search(
        r"(\d{1,3}(?:\.\d{1,3}){3})\s+port\s+(\d+)",
        rest,
        re.IGNORECASE,
    )
    if ip_port_match:
        ip = ip_port_match.group(1)
        port = ip_port_match.group(2)

    # mensagem de erro principal (antes de " in C:\..." se existir)
    msg_main = rest
    in_idx = rest.lower().find(" in ")
    if in_idx != -1:
        msg_main = rest[:in_idx].strip()

    # Heurística de causa pra cURL / network
    if "curl error" in rest.lower() or ip_port_match:
        cause_group = "network"
        if ip and port:
            # tenta achar "Connection refused", "timed out", etc
            reason_match = re.search(
                r":\s*([^:]+)$",
                msg_main,
            )
            human_reason = reason_match.group(1).strip() if reason_match else "Erro de conexão"

            cause_reason = f"cURL falhou ao conectar em {ip}:{port} ({human_reason})"
            cause_action = f"Verificar serviço/porta {port} em {ip} (controller / backend) ou regras de firewall"
        else:
            cause_reason = msg_main
            cause_action = "Verificar conectividade de rede/serviço referenciado pelo cURL"

    # fallback genérico
    if cause_group is None:
        cause_group = "aplicacao"
        cause_reason = msg_main
        cause_action = "Avaliar stack trace e corrigir causa raiz no código PHP"

    return {
        "timestamp": timestamp,
        "level": level,
        "message": rest,
        "cause_group": cause_group,
        "cause_reason": cause_reason,
        "cause_action": cause_action,
    }


# =====================================
# Ingestão de arquivo texto (upload)
# =====================================

def ingest_plaintext_log(
    stream,
    source: str = "upload",
    default_host: str = "upload-host",
) -> None:
    """
    Lê um arquivo de log texto linha a linha e insere no banco.

    Pipeline:
      1) Tenta parser específico (PHP error log).
      2) Se não bater, usa parser genérico baseado em timestamp ISO e palavras-chave de nível.
    """
    conn = get_connection()
    cur = conn.cursor()

    level_patterns = {
        "ERROR": re.compile(r"\bERROR\b", re.IGNORECASE),
        "WARNING": re.compile(r"\bWARN(ING)?\b", re.IGNORECASE),
        "INFO": re.compile(r"\bINFO\b", re.IGNORECASE),
        "CRITICAL": re.compile(r"\bCRITICAL\b", re.IGNORECASE),
        "NOTICE": re.compile(r"\bNOTICE\b", re.IGNORECASE),
    }

    ts_regex = re.compile(
        r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})"
    )

    for raw in stream:
        if isinstance(raw, bytes):
            line = raw.decode("utf-8", errors="ignore").strip()
        else:
            line = str(raw).strip()

        if not line:
            continue

        # 1) Tenta parser específico PHP error log
        php_parsed = parse_php_error_line(line)
        if php_parsed:
            timestamp = php_parsed["timestamp"]
            level = php_parsed["level"]
            message = php_parsed["message"]
            cause_group = php_parsed["cause_group"]
            cause_reason = php_parsed["cause_reason"]
            cause_action = php_parsed["cause_action"]

            cur.execute(
                """
                INSERT INTO logs
                (timestamp, source, level, host, message, cause_group, cause_reason, cause_action)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    source,
                    level,
                    default_host,
                    message,
                    cause_group,
                    cause_reason,
                    cause_action,
                ),
            )
            continue  # vai pra próxima linha

        # 2) Parser genérico (ISO timestamp etc.)
        m_ts = ts_regex.match(line)
        if m_ts:
            timestamp = m_ts.group(1)
            message = line[len(timestamp):].strip()
        else:
            timestamp = datetime_utc_now()
            message = line

        level = "INFO"
        for lvl, patt in level_patterns.items():
            if patt.search(line):
                level = lvl.upper()
                break

        cur.execute(
            """
            INSERT INTO logs
            (timestamp, source, level, host, message, cause_group, cause_reason, cause_action)
            VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL)
            """,
            (timestamp, source, level, default_host, message),
        )

    conn.commit()
    conn.close()


# =====================================
# Funções para a DASHBOARD
# =====================================

def get_summary() -> Dict[str, Optional[int]]:
    """
    Coleta resumo global dos logs para a dashboard.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS c FROM logs")
    total = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*) AS c FROM logs WHERE level = 'ERROR'")
    errors = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*) AS c FROM logs WHERE level = 'WARNING'")
    warnings = cur.fetchone()["c"]

    cur.execute("SELECT MIN(timestamp) AS first_ts, MAX(timestamp) AS last_ts FROM logs")
    row = cur.fetchone()
    first_ts = row["first_ts"]
    last_ts = row["last_ts"]

    conn.close()

    return {
        "total": total,
        "errors": errors,
        "warnings": warnings,
        "first_ts": first_ts,
        "last_ts": last_ts,
    }


def get_latest_logs(
    limit: int = 100,
    offset: int = 0,
    level: Optional[str] = None,
) -> Tuple[List[str], List[Dict]]:
    """
    Retorna os logs mais recentes para a tabela da dashboard.
    """
    conn = get_connection()
    cur = conn.cursor()

    base_sql = """
        SELECT
            id,
            timestamp,
            source,
            level,
            host,
            message,
            cause_group,
            cause_reason,
            cause_action
        FROM logs
    """

    params: List = []
    where_clauses: List[str] = []

    if level:
        where_clauses.append("level = ?")
        params.append(level)

    if where_clauses:
        base_sql += " WHERE " + " AND ".join(where_clauses)

    base_sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cur.execute(base_sql, params)
    rows_sql = cur.fetchall()
    conn.close()

    columns = [
        "id",
        "timestamp",
        "source",
        "level",
        "host",
        "message",
        "cause_group",
        "cause_reason",
        "cause_action",
    ]

    rows: List[Dict] = [
        {col: r[col] for col in columns}
        for r in rows_sql
    ]

    return columns, rows
