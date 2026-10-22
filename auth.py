import re

from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash
)
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, current_user
)
from sqlalchemy import or_

from models import db, User

auth = Blueprint("auth", __name__, url_prefix="/auth")

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to continue."


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@auth.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not re.fullmatch(r"[A-Za-z0-9_]{3,30}", username):
            flash(
                "Username must be 3-30 characters using letters, numbers or underscores.",
                "error"
            )
            return render_template("register.html")

        if len(email) > 120 or not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+", email
        ):
            flash("Enter a valid email address.", "error")
            return render_template("register.html")

        if len(password) < 8 or len(password) > 128:
            flash("Password must contain 8-128 characters.", "error")
            return render_template("register.html")

        existing_user = db.session.execute(
            db.select(User).where(
                or_(
                    User.username == username,
                    User.email == email
                )
            )
        ).scalar_one_or_none()

        if existing_user:
            flash("Username or email is already registered.", "error")
            return render_template("register.html")

        user = User(username=username, email=email)
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash("Your ABOSTIFY account is ready!", "success")
        return redirect(url_for("dashboard"))

    return render_template("register.html")


@auth.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        identity = request.form.get("identity", "").strip()
        password = request.form.get("password", "")

        user = db.session.execute(
            db.select(User).where(
                or_(
                    User.username == identity,
                    User.email == identity.lower()
                )
            )
        ).scalar_one_or_none()

        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("dashboard"))

        flash("Invalid username/email or password.", "error")

    return render_template("login.html")


@auth.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))
