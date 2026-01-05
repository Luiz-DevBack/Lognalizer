import paramiko
from pathlib import Path
from .ingest import ingest_zabbix_server


def fetch_remote_file(host: str, user: str, password: str,
                      remote_path: str, local_path: str) -> Path:
    """
    Baixa um arquivo remoto via SFTP (SSH) e salva localmente.
    """
    local = Path(local_path)
    local.parent.mkdir(parents=True, exist_ok=True)

    print(f"[DEBUG] Conectando em {host} via SSH como {user}...")
    transport = paramiko.Transport((host, 22))
    transport.connect(username=user, password=password)

    print(f"[DEBUG] Baixando {remote_path} -> {local} ...")
    sftp = paramiko.SFTPClient.from_transport(transport)
    sftp.get(remote_path, str(local))
    sftp.close()
    transport.close()
    print(f"[DEBUG] Download concluído. Tamanho: {local.stat().st_size} bytes")

    return local


def remote_ingest_zbx_server(host: str, user: str, password: str,
                             remote_path: str, alias: str = "zbx-server"):
    """
    Busca o zabbix_server.log em uma VM remota via SSH
    e ingere no banco local.
    """
    tmpfile = f"/tmp/{alias}_zabbix_server.log"
    local_path = fetch_remote_file(host, user, password, remote_path, tmpfile)

    print(f"[DEBUG] Ingerindo {local_path} como host={alias} ...")
    count = ingest_zabbix_server(str(local_path), host=alias)
    print(f"[DEBUG] Ingest finalizada: {count} linhas.")
    return count

