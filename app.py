import os

from flask import Flask, render_template
from flask_login import current_user, login_required
from flask_wtf.csrf import CSRFProtect

from config import Config
from models import db, User
from sqlalchemy import inspect, text
from auth import auth, login_manager
from profiles import profiles


app = Flask(__name__)
app.config.from_object(Config)

# Production mein SECRET_KEY environment variable set karna.
if not os.environ.get("SECRET_KEY"):
    app.config["SECRET_KEY"] = "local-development-key-change-before-deploy"

csrf = CSRFProtect(app)

db.init_app(app)
login_manager.init_app(app)

app.register_blueprint(auth)
app.register_blueprint(profiles)


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

    table_name = User.__tablename__
    inspector = inspect(db.engine)

    existing_columns = {
        column["name"]
        for column in inspector.get_columns(table_name)
    }

    column_definitions = {
        "display_name": "VARCHAR(60)",
        "bio": "VARCHAR(300)",
        "location": "VARCHAR(100)",
        "website": "VARCHAR(200)",
    }

    quoted_table = (
        db.engine.dialect.identifier_preparer.quote(table_name)
    )

    with db.engine.begin() as connection:
        for column_name, column_type in column_definitions.items():
            if column_name not in existing_columns:
                quoted_column = (
                    db.engine.dialect.identifier_preparer
                    .quote(column_name)
                )

                connection.execute(
                    text(
                        f"ALTER TABLE {quoted_table} "
                        f"ADD COLUMN {quoted_column} {column_type}"
                    )
                )

                print(f"Database migration: added {column_name}")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
