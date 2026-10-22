import os
from pathlib import Path

from flask import Flask, jsonify, render_template
from flask_login import current_user, login_required
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import inspect, text

from config import Config
from models import db, User, Post
from auth import auth, login_manager
from profiles import profiles
from social import social
from productivity import productivity
from messaging import messaging
from community_api import community_api
from business_api import business_api
import extended_models

app = Flask(__name__)
app.config.from_object(Config)

app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = Path(app.static_folder) / "uploads" / "posts"
app.config["UPLOAD_FOLDER"].mkdir(parents=True, exist_ok=True)

csrf = CSRFProtect(app)
db.init_app(app)
login_manager.init_app(app)

for blueprint in (
    auth, profiles, social, productivity,
    messaging, community_api, business_api,
):
    app.register_blueprint(blueprint)


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", user=current_user)



@app.get("/productivity")
@login_required
def productivity_center():
    return render_template("productivity.html", user=current_user)


@app.get("/health")
def health():
    return jsonify({
        "app": "ABOSTIFY",
        "status": "healthy",
        "version": "toy-0.4",
    })


@app.get("/api/me")
@login_required
def current_user_api():
    return jsonify({
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "display_name": current_user.display_name,
        "bio": current_user.bio,
        "location": current_user.location,
        "website": current_user.website,
    })


def migrate_missing_columns():
    migrations = {
        User.__tablename__: {
            "display_name": "VARCHAR(60)",
            "bio": "VARCHAR(300)",
            "location": "VARCHAR(100)",
            "website": "VARCHAR(200)",
        },
        Post.__tablename__: {
            "image_filename": "VARCHAR(255)",
        },
    }

    inspector = inspect(db.engine)
    preparer = db.engine.dialect.identifier_preparer

    with db.engine.begin() as connection:
        for table_name, columns in migrations.items():
            if not inspector.has_table(table_name):
                continue

            existing = {
                column["name"]
                for column in inspector.get_columns(table_name)
            }

            for column_name, column_type in columns.items():
                if column_name in existing:
                    continue

                table = preparer.quote(table_name)
                column = preparer.quote(column_name)

                connection.execute(text(
                    f"ALTER TABLE {table} "
                    f"ADD COLUMN {column} {column_type}"
                ))

                print(f"Added database column {table_name}.{column_name}")


with app.app_context():
    db.create_all()
    migrate_missing_columns()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
