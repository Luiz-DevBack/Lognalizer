from flask import Flask, render_template, send_from_directory
import os

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static"
)

# Rota principal
@app.route("/")
def index():
    return render_template("dashboard.html")

# Rota para arquivos CSS e JS fora da pasta static
@app.route("/assets/<path:filename>")
def custom_assets(filename):
    return send_from_directory("assets", filename)

@app.route("/frontend/<path:filename>")
def custom_frontend(filename):
    return send_from_directory("frontend", filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
