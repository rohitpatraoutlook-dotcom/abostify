from models import db
from extended_models import ActivityLog, Notification


def record_activity(
    workspace_id, actor_id, action, object_type=None,
    object_id=None, details=None, ip_address=None
):
    """Add an activity record to the current transaction; do not commit."""
    item = ActivityLog(
        workspace_id=workspace_id,
        actor_id=actor_id,
        action=str(action)[:100],
        object_type=str(object_type)[:80] if object_type else None,
        object_id=object_id,
        details=details if isinstance(details, dict) else {},
        ip_address=str(ip_address)[:45] if ip_address else None,
    )
    db.session.add(item)
    return item


def add_notification(
    recipient_id, title, body, kind="general",
    actor_id=None, object_type=None, object_id=None
):
    """Add a notification to the current transaction; do not commit."""
    message = f"{str(title).strip()}: {str(body).strip()}"[:500]
    item = Notification(
        recipient_id=recipient_id,
        actor_id=actor_id,
        notification_type=str(kind)[:40],
        object_type=str(object_type)[:40] if object_type else None,
        object_id=object_id,
        message=message or "You have a new notification",
    )
    db.session.add(item)
    return item
