from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(
        db.String(30),
        unique=True,
        nullable=False,
        index=True
    )

    email = db.Column(
        db.String(120),
        unique=True,
        nullable=False,
        index=True
    )

    password_hash = db.Column(
        db.String(256),
        nullable=False
    )

    display_name = db.Column(db.String(60), nullable=True)
    bio = db.Column(db.String(300), nullable=True)
    location = db.Column(db.String(100), nullable=True)
    website = db.Column(db.String(200), nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Post(db.Model):
    __tablename__ = "post"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        index=True
    )

    content = db.Column(db.String(2000), nullable=False)
    image_filename = db.Column(db.String(255), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now(),
        nullable=False,
        index=True
    )

    author = db.relationship(
        "User",
        backref=db.backref("posts", lazy="dynamic")
    )

    likes = db.relationship(
        "PostLike",
        back_populates="post",
        cascade="all, delete-orphan"
    )

    comments = db.relationship(
        "PostComment",
        back_populates="post",
        cascade="all, delete-orphan",
        order_by="PostComment.created_at.asc()"
    )


class PostLike(db.Model):
    __tablename__ = "post_like"

    id = db.Column(db.Integer, primary_key=True)

    post_id = db.Column(
        db.Integer,
        db.ForeignKey("post.id"),
        nullable=False
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now(),
        nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint(
            "post_id",
            "user_id",
            name="unique_post_like"
        ),
    )

    post = db.relationship("Post", back_populates="likes")
    user = db.relationship("User")


class PostComment(db.Model):
    __tablename__ = "post_comment"

    id = db.Column(db.Integer, primary_key=True)

    post_id = db.Column(
        db.Integer,
        db.ForeignKey("post.id"),
        nullable=False,
        index=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    content = db.Column(db.String(500), nullable=False)

    created_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now(),
        nullable=False
    )

    post = db.relationship("Post", back_populates="comments")
    author = db.relationship("User")


class Follow(db.Model):
    __tablename__ = "follow"

    id = db.Column(db.Integer, primary_key=True)

    follower_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        index=True
    )

    followed_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
        index=True
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now(),
        nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint(
            "follower_id",
            "followed_id",
            name="unique_follow_relationship"
        ),
        db.CheckConstraint(
            "follower_id != followed_id",
            name="prevent_self_follow"
        ),
    )

    follower = db.relationship(
        "User",
        foreign_keys=[follower_id],
        backref="following_relationships"
    )

    followed = db.relationship(
        "User",
        foreign_keys=[followed_id],
        backref="follower_relationships"
    )
