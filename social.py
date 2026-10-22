from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
)
from flask_login import current_user, login_required
from sqlalchemy import select
from models import db, Post, PostLike, PostComment, Follow, User
social = Blueprint("social", __name__)


@social.get("/feed")
def feed():
    posts = db.session.execute(
        select(Post)
        .order_by(Post.created_at.desc(), Post.id.desc())
        .limit(50)
    ).scalars().all()

    liked_post_ids = set()

    if current_user.is_authenticated:
        liked_post_ids = set(
            db.session.execute(
                select(PostLike.post_id).where(
                    PostLike.user_id == current_user.id
                )
            ).scalars().all()
        )

    return render_template(
        "feed.html",
        posts=posts,
        liked_post_ids=liked_post_ids,
    )


@social.route("/posts/create", methods=["GET", "POST"])
@login_required
def create_post():
    if request.method == "POST":
        content = request.form.get("content", "").strip()

        if not content:
            flash("Please write something before publishing.", "error")
        elif len(content) > 2000:
            flash("Posts cannot exceed 2000 characters.", "error")
        else:
            post = Post(
                user_id=current_user.id,
                content=content,
            )

            db.session.add(post)
            db.session.commit()

            flash("Your post has been published.", "success")
            return redirect(url_for("social.feed"))

    return render_template("create_post.html")


@social.post("/posts/<int:post_id>/like")
@login_required
def toggle_like(post_id):
    post = db.session.get(Post, post_id)

    if post is None:
        flash("Post not found.", "error")
        return redirect(url_for("social.feed"))

    existing_like = db.session.execute(
        select(PostLike).where(
            PostLike.post_id == post_id,
            PostLike.user_id == current_user.id,
        )
    ).scalar_one_or_none()

    if existing_like:
        db.session.delete(existing_like)
    else:
        db.session.add(
            PostLike(
                post_id=post_id,
                user_id=current_user.id,
            )
        )

    db.session.commit()

    return redirect(
        request.referrer or url_for("social.feed")
    )


@social.post("/posts/<int:post_id>/comment")
@login_required
def add_comment(post_id):
    post = db.session.get(Post, post_id)

    if post is None:
        flash("Post not found.", "error")
        return redirect(url_for("social.feed"))

    content = request.form.get("content", "").strip()

    if not content:
        flash("Comment cannot be empty.", "error")
    elif len(content) > 500:
        flash("Comments cannot exceed 500 characters.", "error")
    else:
        comment = PostComment(
            post_id=post_id,
            user_id=current_user.id,
            content=content,
        )

        db.session.add(comment)
        db.session.commit()

    return redirect(
        request.referrer or url_for("social.feed")
    )


@social.post("/users/<string:username>/follow")
@login_required
def toggle_follow(username):
    target_user = db.session.execute(
        select(User).where(User.username == username)
    ).scalar_one_or_none()

    if target_user is None:
        flash("User not found.", "error")
        return redirect(url_for("social.feed"))

    if target_user.id == current_user.id:
        flash("You cannot follow yourself.", "error")
        return redirect(
            url_for("profiles.view", username=username)
        )

    existing_follow = db.session.execute(
        select(Follow).where(
            Follow.follower_id == current_user.id,
            Follow.followed_id == target_user.id
        )
    ).scalar_one_or_none()

    if existing_follow:
        db.session.delete(existing_follow)
        flash(
            f"You unfollowed {target_user.username}.",
            "success"
        )
    else:
        db.session.add(
            Follow(
                follower_id=current_user.id,
                followed_id=target_user.id
            )
        )
        flash(
            f"You are now following {target_user.username}.",
            "success"
        )

    db.session.commit()

    return redirect(
        url_for("profiles.view", username=username)
    )


@social.get("/people")
def discover_people():
    people = db.session.execute(
        select(User)
        .order_by(User.username.asc())
        .limit(100)
    ).scalars().all()

    follower_counts = dict(
        db.session.execute(
            select(
                Follow.followed_id,
                db.func.count(Follow.id)
            )
            .group_by(Follow.followed_id)
        ).all()
    )

    following_ids = set()

    if current_user.is_authenticated:
        following_ids = set(
            db.session.execute(
                select(Follow.followed_id).where(
                    Follow.follower_id == current_user.id
                )
            ).scalars().all()
        )

    return render_template(
        "people.html",
        people=people,
        follower_counts=follower_counts,
        following_ids=following_ids,
    )


@social.get("/search")
def search_users():
    query = request.args.get("q", "").strip()[:60]
    people = []

    if query:
        search_pattern = f"%{query}%"

        people = db.session.execute(
            select(User)
            .where(
                db.or_(
                    User.username.ilike(search_pattern),
                    User.display_name.ilike(search_pattern)
                )
            )
            .order_by(User.username.asc())
            .limit(50)
        ).scalars().all()

    follower_counts = dict(
        db.session.execute(
            select(
                Follow.followed_id,
                db.func.count(Follow.id)
            )
            .group_by(Follow.followed_id)
        ).all()
    )

    following_ids = set()

    if current_user.is_authenticated:
        following_ids = set(
            db.session.execute(
                select(Follow.followed_id).where(
                    Follow.follower_id == current_user.id
                )
            ).scalars().all()
        )

    return render_template(
        "search_users.html",
        query=query,
        people=people,
        follower_counts=follower_counts,
        following_ids=following_ids,
    )


@social.get("/following")
@login_required
def following_feed():
    posts = db.session.execute(
        select(Post)
        .join(
            Follow,
            Follow.followed_id == Post.user_id
        )
        .where(
            Follow.follower_id == current_user.id
        )
        .order_by(
            Post.created_at.desc(),
            Post.id.desc()
        )
        .limit(100)
    ).scalars().unique().all()

    liked_post_ids = set(
        db.session.execute(
            select(PostLike.post_id).where(
                PostLike.user_id == current_user.id
            )
        ).scalars().all()
    )

    return render_template(
        "following_feed.html",
        posts=posts,
        liked_post_ids=liked_post_ids,
    )
