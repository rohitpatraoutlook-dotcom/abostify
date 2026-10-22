import re
from urllib.parse import urlparse

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required
from sqlalchemy import select

from models import db, User

profiles = Blueprint("profiles", __name__, url_prefix="/profile")


def valid_website(value):
    if not value:
        return True

    if len(value) > 200:
        return False

    candidate = value if "://" in value else "https://" + value
    parsed = urlparse(candidate)

    return (
        parsed.scheme in ("http", "https")
        and bool(parsed.hostname)
        and "." in parsed.hostname
        and not any(ch.isspace() for ch in candidate)
    )


@profiles.route("/edit", methods=["GET", "POST"])
@login_required
def edit():
    if request.method == "POST":
        display_name = request.form.get("display_name", "").strip()
        bio = request.form.get("bio", "").strip()
        location = request.form.get("location", "").strip()
        website = request.form.get("website", "").strip()

        if len(display_name) > 60:
            flash("Display name must be 60 characters or less.", "error")
        elif len(bio) > 300:
            flash("Bio must be 300 characters or less.", "error")
        elif len(location) > 100:
            flash("Location must be 100 characters or less.", "error")
        elif not valid_website(website):
            flash("Enter a valid website address.", "error")
        else:
            current_user.display_name = display_name or None
            current_user.bio = bio or None
            current_user.location = location or None

            if website and "://" not in website:
                website = "https://" + website

            current_user.website = website or None

            db.session.commit()
            flash("Profile updated successfully!", "success")
            return redirect(
                url_for("profiles.view", username=current_user.username)
            )

    return render_template("edit_profile.html", user=current_user)


@profiles.get("/<string:username>")
def view(username):
    user = db.session.execute(
        select(User).where(User.username == username)
    ).scalar_one_or_none()

    if user is None:
        return render_template("profile_not_found.html"), 404

    return render_template(
        "profile.html",
        profile_user=user,
        is_owner=current_user.is_authenticated and current_user.id == user.id
    )
