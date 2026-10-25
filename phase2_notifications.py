from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from models import db
from company_portal import Company, CompanyEmployee
from extended_models import ActivityLog, Notification
from phase2_events import add_notification

notifications_api = Blueprint(
    "notifications_api", __name__, url_prefix="/api/v2"
)


def notify_error(message, status=400):
    return jsonify({"ok": False, "error": message}), status


def active_member(company_id, user_id):
    return CompanyEmployee.query.filter_by(
        company_id=company_id,
        user_id=user_id,
        status="active"
    ).first()


def notification_json(item):
    message = item.message or ""
    if ": " in message:
        title, body = message.split(": ", 1)
    else:
        title = item.notification_type.replace("_", " ").title()
        body = message

    return {
        "id": item.id,
        "type": item.notification_type,
        "title": title,
        "body": body,
        "is_read": item.is_read,
        "created_at": item.created_at.isoformat()
        if item.created_at else None
    }


@notifications_api.get("/notifications")
@login_required
def list_notifications():
    query = Notification.query.filter_by(recipient_id=current_user.id)

    if request.args.get("unread", "").lower() in ("1", "true", "yes"):
        query = query.filter_by(is_read=False)

    items = query.order_by(
        Notification.created_at.desc()
    ).limit(100).all()

    unread_count = Notification.query.filter_by(
        recipient_id=current_user.id,
        is_read=False
    ).count()

    return jsonify({
        "ok": True,
        "unread_count": unread_count,
        "notifications": [notification_json(x) for x in items]
    })


@notifications_api.post("/notifications/<int:notification_id>/read")
@login_required
def mark_read(notification_id):
    item = Notification.query.filter_by(
        id=notification_id,
        recipient_id=current_user.id
    ).first_or_404()

    item.is_read = True
    db.session.commit()
    return jsonify({"ok": True, "message": "Marked as read"})


@notifications_api.post("/notifications/read-all")
@login_required
def mark_all_read():
    Notification.query.filter_by(
        recipient_id=current_user.id,
        is_read=False
    ).update({"is_read": True}, synchronize_session=False)

    db.session.commit()
    return jsonify({"ok": True, "message": "All notifications marked as read"})


@notifications_api.get("/companies/<int:cid>/activity")
@login_required
def company_activity(cid):
    if not active_member(cid, current_user.id):
        return notify_error("Active company membership required", 403)

    company = Company.query.filter_by(id=cid, is_active=True).first()
    if not company:
        return notify_error("Company not found", 404)

    items = (
        ActivityLog.query
        .filter_by(workspace_id=company.workspace_id)
        .order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
        .limit(100)
        .all()
    )

    return jsonify({
        "ok": True,
        "company_id": cid,
        "activities": [
            {
                "id": item.id,
                "action": item.action,
                "object_type": item.object_type,
                "object_id": item.object_id,
                "details": item.details or {},
                "actor": item.actor.username if item.actor else "System",
                "created_at": item.created_at.isoformat()
                if item.created_at else None,
            }
            for item in items
        ],
    })


def create_notification(user_id, title, body, kind="general"):
    """Backward-compatible helper; caller owns the transaction."""
    return add_notification(user_id, title, body, kind=kind)
