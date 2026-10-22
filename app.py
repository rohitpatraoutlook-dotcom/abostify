import os

from flask import Flask, render_template
from flask_login import current_user, login_required
from flask_wtf.csrf import CSRFProtect

from config import Config
from models import db
from auth import auth, login_manager


app = Flask(__name__)
app.config.from_object(Config)

# Production mein SECRET_KEY environment variable set karna.
if not os.environ.get("SECRET_KEY"):
    app.config["SECRET_KEY"] = "local-development-key-change-before-deploy"

csrf = CSRFProtect(app)

db.init_app(app)
login_manager.init_app(app)

app.register_blueprint(auth)


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", user=current_user)


@app.get("/health")
def health():
    return {
        "app": "ABOSTIFY",
        "status": "healthy",
        "version": "toy-0.2"
    }


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
