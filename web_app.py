from pathlib import Path

from flask import (
    Flask,
    render_template,
    jsonify,
    request,
    redirect,
    url_for,
)
from werkzeug.utils import secure_filename

from src import models

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "logs_examples"
UPLOAD_DIR.mkdir(exist_ok=True)


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "Frontend" / "templates"),
        static_folder=str(BASE_DIR / "static"),
        static_url_path="/static",
    )

    # ------------ CONTEXTO GLOBAL ------------

    @app.context_processor
    def inject_globals():
        return {
            "app_name": "Magiccomp Log Analyzer",
        }

    # ------------ ROTAS WEB ------------

    @app.route("/")
    def dashboard():
        summary = models.get_summary()
        _, event_rows = models.get_latest_logs(limit=50)

        return render_template(
            "dashboard.html",
            summary=summary,
            event_rows=event_rows,
        )

    @app.route("/logs")
    def logs_page():
        page = max(int(request.args.get("page", 1)), 1)
        per_page = 200
        offset = (page - 1) * per_page

        columns, rows = models.get_latest_logs(limit=per_page, offset=offset)

        return render_template(
            "logs.html",
            columns=columns,
            rows=rows,
            page=page,
            per_page=per_page,
        )

    @app.route("/logs/iframe")
    def logs_iframe():
        columns, rows = models.get_latest_logs(limit=200)
        return render_template("logs_iframe.html", columns=columns, rows=rows)

    # ------------ UPLOAD DE LOGS ------------

    @app.route("/upload-logs", methods=["GET", "POST"])
    def upload_logs():
        """
        Tela de upload com drag & drop.
        Agora valida se o arquivo parece ser um LOG antes de ingerir.
        """
        if request.method == "POST":
            file = request.files.get("logfile")
            if not file or file.filename == "":
                return render_template(
                    "upload_logs.html",
                    error="Nenhum arquivo selecionado.",
                )

            # Primeiro: valida se parece log
            # Lê só um pedaço do stream pra inspecionar
            if not models.is_probably_log(file.stream, filename=file.filename):
                # Volta o stream pro início só por segurança
                file.stream.seek(0)
                return render_template(
                    "upload_logs.html",
                    error="O arquivo não parece ser um log de texto. Envie um .log/.txt com linhas de log.",
                )

            # Se passou na validação, salva uma cópia e ingere
            filename = secure_filename(file.filename)
            save_path = UPLOAD_DIR / filename

            # Salva cópia física
            file.stream.seek(0)
            with open(save_path, "wb") as f:
                f.write(file.read())

            # Volta ponteiro pro início pra ingestão no SQLite
            file.stream.seek(0)
            models.ingest_plaintext_log(
                file.stream,
                source=f"upload:{filename}",
                default_host="upload-host",
            )

            return render_template(
                "upload_logs.html",
                success=f"Arquivo {filename} ingerido com sucesso!",
            )

        # GET
        return render_template("upload_logs.html")

    # ------------ AÇÕES DOS BOTÕES (PLAYBOOK) ------------

    @app.route("/action/execute_block", methods=["POST"])
    def action_execute_block():
        models.insert_log(
            timestamp=models.datetime_utc_now(),
            source="action:ddos_block",
            level="INFO",
            host="wan-gateway-04",
            message="Ação EXECUTE BLOCK disparada via dashboard (simulação iptables DROP 45.22.0.0/16).",
            cause_group="seguranca",
            cause_reason="Mitigação DDoS manual",
            cause_action="BLOCK_SUBNET",
        )
        return redirect(url_for("dashboard"))

    @app.route("/action/db_scale_out", methods=["POST"])
    def action_db_scale_out():
        models.insert_log(
            timestamp=models.datetime_utc_now(),
            source="action:db_scale_out",
            level="INFO",
            host="db-cluster-01",
            message="Ação DB SCALE OUT disparada via dashboard (simulação provisionamento Read Replica).",
            cause_group="banco_dados",
            cause_reason="Escalonamento horizontal planejado",
            cause_action="PROVISION_READ_REPLICA",
        )
        return redirect(url_for("dashboard"))

    @app.route("/action/disk_cleanup", methods=["POST"])
    def action_disk_cleanup():
        models.insert_log(
            timestamp=models.datetime_utc_now(),
            source="action:disk_cleanup",
            level="WARNING",
            host="log-srv-02",
            message="Ação DISK CLEANUP disparada via dashboard (simulação limpeza de /var/log).",
            cause_group="hardware",
            cause_reason="Disco em alta utilização",
            cause_action="RUN_CLEANUP",
        )
        return redirect(url_for("dashboard"))

    # ------------ APIS JSON ------------

    @app.route("/api/summary")
    def api_summary():
        return jsonify(models.get_summary())

    @app.route("/api/logs")
    def api_logs():
        limit = int(request.args.get("limit", 100))
        level = request.args.get("level")
        columns, rows = models.get_latest_logs(limit=limit, level=level)
        return jsonify({"columns": columns, "rows": rows})

    return app


if __name__ == "__main__":
    models.init_db()
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)
