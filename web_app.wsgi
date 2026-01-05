import sys
import os

project_path = "/home/magiccomp/magicomp-log-analyzer"
venv_path = "/home/magiccomp/magicomp-log-analyzer/venv"

# Garante que o projeto está no PYTHONPATH
if project_path not in sys.path:
    sys.path.insert(0, project_path)

# Ativa o ambiente virtual (opcional, mas ajuda)
activate_this = os.path.join(venv_path, "bin", "activate_this.py")
if os.path.exists(activate_this):
    with open(activate_this) as f:
        exec(f.read(), dict(__file__=activate_this))

from web_app import app as application  # <- aqui é o seu Flask app
