import re
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import or_

from models import db, User, Post
from extended_models import (
    Notification,
    Community,
    CommunityMembership,
    PostBookmark,
)

community_api = Blueprint("community_api", __name__, url_prefix="/api")


def error(message, status=400):
    return jsonify({"error": message}), status


def now_utc():
    return datetime.now(timezone.utc)


def notification_json(item):
    return {
        "id": item.id,
        "actor_id": item.actor_id,
        "type": item.notification_type,
        "object_type": item.object_type,
        "object_id": item.object_id,
        "message": item.message,
        "is_read": item.is_read,
        "created_at": (
            item.created_at.isoformat()
            if item.created_at else None
        ),
    }


def community_json(item, membership=None):
    return {
        "id": item.id,
        "name": item.name,
        "slug": item.slug,
        "description": item.description,
        "owner_id": item.owner_id,
        "visibility": item.visibility,
        "is_archived": item.is_archived,
        "membership_status": (
            membership.status if membership else None
        ),
        "membership_role": (
            membership.role if membership else None
        ),
    }


def get_membership(community_id, user_id):
    return CommunityMembership.query.filter_by(
        community_id=community_id,
        user_id=user_id,
    ).first()


def active_membership(community_id, user_id):
    membership = get_membership(community_id, user_id)
    if membership and membership.status == "active":
        return membership
    return None


def create_notification(
    recipient_id,
    notification_type,
    message,
    actor_id=None,
    object_type=None,
    object_id=None,
):
    if recipient_id == actor_id:
        return None

    item = Notification(
        recipient_id=recipient_id,
        actor_id=actor_id,
        notification_type=notification_type,
        message=message[:500],
        object_type=object_type,
        object_id=object_id,
        is_read=False,
    )
    db.session.add(item)
    return item


# --------------------------------------------------
# NOTIFICATIONS
# --------------------------------------------------

@community_api.get("/notifications")
@login_required
def list_notifications():
    limit = request.args.get("limit", 30, type=int)
    limit = max(1, min(limit or 30, 100))

    query = Notification.query.filter_by(
        recipient_id=current_user.id
    )

    unread_only = request.args.get("unread", "").lower()
    if unread_only in ("1", "true", "yes"):
        query = query.filter_by(is_read=False)

    items = query.order_by(
        Notification.id.desc()
    ).limit(limit).all()

    unread_count = Notification.query.filter_by(
        recipient_id=current_user.id,
        is_read=False,
    ).count()

    return jsonify({
        "notifications": [
            notification_json(item) for item in items
        ],
        "unread_count": unread_count,
    })


@community_api.post("/notifications/read-all")
@login_required
def read_all_notifications():
    Notification.query.filter_by(
        recipient_id=current_user.id,
        is_read=False,
    ).update(
        {"is_read": True},
        synchronize_session=False,
    )
    db.session.commit()
    return jsonify({"message": "All notifications marked as read"})


@community_api.patch("/notifications/<int:notification_id>")
@login_required
def update_notification(notification_id):
    item = db.session.get(Notification, notification_id)

    if not item or item.recipient_id != current_user.id:
        return error("Notification not found", 404)

    data = request.get_json(silent=True) or {}

    if "is_read" not in data:
        return error("is_read is required")

    if not isinstance(data["is_read"], bool):
        return error("is_read must be true or false")

    item.is_read = data["is_read"]
    db.session.commit()

    return jsonify({
        "message": "Notification updated",
        "notification": notification_json(item),
    })


@community_api.delete("/notifications/<int:notification_id>")
@login_required
def delete_notification(notification_id):
    item = db.session.get(Notification, notification_id)

    if not item or item.recipient_id != current_user.id:
        return error("Notification not found", 404)

    db.session.delete(item)
    db.session.commit()
    return jsonify({"message": "Notification deleted"})


# --------------------------------------------------
# COMMUNITIES
# --------------------------------------------------

@community_api.route("/communities", methods=["GET", "POST"])
@login_required
def communities():
    if request.method == "GET":
        query = Community.query.filter_by(is_archived=False)

        visibility = request.args.get("visibility")
        if visibility in ("public", "private"):
            query = query.filter_by(visibility=visibility)

        items = query.order_by(Community.id.desc()).limit(100).all()
        result = []

        for item in items:
            membership = get_membership(item.id, current_user.id)

            if item.visibility == "private":
                if not membership or membership.status != "active":
                    continue

            result.append(community_json(item, membership))

        return jsonify({"communities": result})

    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    description = str(data.get("description", "")).strip()
    visibility = str(data.get("visibility", "public")).strip().lower()

    if len(name) < 3 or len(name) > 80:
        return error("Community name must be 3-80 characters")

    if len(description) > 1000:
        return error("Description cannot exceed 1000 characters")

    if visibility not in ("public", "private"):
        return error("Visibility must be public or private")

    base_slug = re.sub(
        r"[^a-z0-9]+",
        "-",
        name.lower(),
    ).strip("-")[:70]

    if not base_slug:
        return error("Community name must contain letters or numbers")

    slug = base_slug
    suffix = 2

    while Community.query.filter_by(slug=slug).first():
        slug = f"{base_slug[:65]}-{suffix}"
        suffix += 1

    item = Community(
        name=name,
        slug=slug,
        description=description,
        owner_id=current_user.id,
        visibility=visibility,
        is_archived=False,
    )

    db.session.add(item)
    db.session.flush()

    db.session.add(
        CommunityMembership(
            community_id=item.id,
            user_id=current_user.id,
            role="owner",
            status="active",
        )
    )

    db.session.commit()

    return jsonify({
        "message": "Community created",
        "community": community_json(
            item, get_membership(item.id, current_user.id)
        ),
    }), 201


@community_api.get("/communities/<int:community_id>")
@login_required
def get_community(community_id):
    item = db.session.get(Community, community_id)

    if not item or item.is_archived:
        return error("Community not found", 404)

    membership = get_membership(item.id, current_user.id)

    if item.visibility == "private":
        if not membership or membership.status != "active":
            return error("Community not found", 404)

    return jsonify({"community": community_json(item, membership)})


@community_api.post("/communities/<int:community_id>/join")
@login_required
def join_community(community_id):
    item = db.session.get(Community, community_id)

    if not item or item.is_archived:
        return error("Community not found", 404)

    if item.owner_id == current_user.id:
        return error("You already own this community", 409)

    membership = get_membership(item.id, current_user.id)

    if membership:
        if membership.status == "banned":
            return error("You cannot join this community", 403)

        if membership.status == "active":
            return error("You are already a member", 409)

        return jsonify({
            "message": "Membership request already exists",
            "status": membership.status,
        })

    status = "active" if item.visibility == "public" else "pending"

    membership = CommunityMembership(
        community_id=item.id,
        user_id=current_user.id,
        role="member",
        status=status,
    )

    db.session.add(membership)

    if status == "active":
        create_notification(
            recipient_id=item.owner_id,
            actor_id=current_user.id,
            notification_type="community_join",
            message=f"{current_user.username} joined {item.name}",
            object_type="community",
            object_id=item.id,
        )

    db.session.commit()

    return jsonify({
        "message": (
            "Joined community"
            if status == "active"
            else "Membership request submitted"
        ),
        "status": status,
    }), 201


@community_api.post("/communities/<int:community_id>/leave")
@login_required
def leave_community(community_id):
    item = db.session.get(Community, community_id)

    if not item:
        return error("Community not found", 404)

    if item.owner_id == current_user.id:
        return error(
            "The owner cannot leave. Transfer ownership or archive the community.",
            403,
        )

    membership = get_membership(item.id, current_user.id)

    if not membership:
        return error("You are not a member", 404)

    db.session.delete(membership)
    db.session.commit()

    return jsonify({"message": "Left community"})


@community_api.get("/communities/<int:community_id>/members")
@login_required
def community_members(community_id):
    item = db.session.get(Community, community_id)

    if not item or item.is_archived:
        return error("Community not found", 404)

    if item.visibility == "private":
        if not active_membership(item.id, current_user.id):
            return error("Community not found", 404)

    memberships = CommunityMembership.query.filter_by(
        community_id=item.id,
        status="active",
    ).all()

    members = []

    for membership in memberships:
        user = db.session.get(User, membership.user_id)
        if user:
            members.append({
                "user_id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "role": membership.role,
            })

    return jsonify({"members": members})


@community_api.patch(
    "/communities/<int:community_id>/members/<int:user_id>"
)
@login_required
def manage_community_member(community_id, user_id):
    item = db.session.get(Community, community_id)

    if not item or item.is_archived:
        return error("Community not found", 404)

    actor_membership = active_membership(item.id, current_user.id)

    if not actor_membership or actor_membership.role not in (
        "owner", "moderator"
    ):
        return error("Insufficient permissions", 403)

    target = get_membership(item.id, user_id)

    if not target:
        return error("Membership not found", 404)

    if target.role == "owner":
        return error("Owner membership cannot be changed here", 403)

    if actor_membership.role == "moderator" and target.role == "moderator":
        return error("Moderators cannot manage other moderators", 403)

    data = request.get_json(silent=True) or {}

    if "status" in data:
        status = str(data["status"]).lower()
        if status not in ("active", "banned"):
            return error("Status must be active or banned")
        target.status = status

    if "role" in data:
        role = str(data["role"]).lower()
        if actor_membership.role != "owner":
            return error("Only the owner can change roles", 403)
        if role not in ("member", "moderator"):
            return error("Role must be member or moderator")
        target.role = role

    db.session.commit()

    return jsonify({
        "message": "Membership updated",
        "user_id": target.user_id,
        "role": target.role,
        "status": target.status,
    })


# --------------------------------------------------
# POST BOOKMARKS
# --------------------------------------------------

@community_api.get("/bookmarks")
@login_required
def list_bookmarks():
    bookmarks = PostBookmark.query.filter_by(
        user_id=current_user.id
    ).order_by(PostBookmark.id.desc()).limit(100).all()

    result = []

    for bookmark in bookmarks:
        post = db.session.get(Post, bookmark.post_id)
        if not post:
            continue

        result.append({
            "bookmark_id": bookmark.id,
            "post_id": post.id,
            "author_id": post.user_id,
            "content": post.content,
            "image_filename": post.image_filename,
            "created_at": (
                post.created_at.isoformat()
                if post.created_at else None
            ),
        })

    return jsonify({"bookmarks": result})


@community_api.post("/posts/<int:post_id>/bookmark")
@login_required
def bookmark_post(post_id):
    post = db.session.get(Post, post_id)

    if not post:
        return error("Post not found", 404)

    existing = PostBookmark.query.filter_by(
        post_id=post_id,
        user_id=current_user.id,
    ).first()

    if existing:
        return jsonify({
            "message": "Post already bookmarked",
            "bookmarked": True,
        })

    bookmark = PostBookmark(
        post_id=post_id,
        user_id=current_user.id,
    )

    db.session.add(bookmark)
    db.session.commit()

    return jsonify({
        "message": "Post bookmarked",
        "bookmarked": True,
        "post_id": post_id,
    }), 201


@community_api.delete("/posts/<int:post_id>/bookmark")
@login_required
def remove_bookmark(post_id):
    bookmark = PostBookmark.query.filter_by(
        post_id=post_id,
        user_id=current_user.id,
    ).first()

    if not bookmark:
        return error("Bookmark not found", 404)

    db.session.delete(bookmark)
    db.session.commit()

    return jsonify({
        "message": "Bookmark removed",
        "bookmarked": False,
    })
