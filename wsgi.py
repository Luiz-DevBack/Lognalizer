# web_app.wsgi

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from web_app import create_app

application = create_app()
