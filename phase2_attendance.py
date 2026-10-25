from datetime import datetime, timezone, date
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from models import db
from company_portal import Company, CompanyEmployee, can_manage_company
from phase2_models import Attendance, LeaveRequest
from phase2_events import record_activity, add_notification

attendance_api = Blueprint(
    "attendance_api", __name__, url_prefix="/api/v2"
)


def error(message, status=400):
    return jsonify({"ok": False, "error": message}), status


def active_member(company_id, user_id):
    return CompanyEmployee.query.filter_by(
        company_id=company_id, user_id=user_id, status="active"
    ).first()


def log_company_activity(cid, action, object_type, object_id=None, details=None):
    company = Company.query.filter_by(id=cid).first()
    if company:
        record_activity(
            workspace_id=company.workspace_id,
            actor_id=current_user.id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            details=details or {},
            ip_address=request.remote_addr,
        )


def parse_day(value):
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def parse_clock(value):
    try:
        result = datetime.fromisoformat(str(value))
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return result
    except (ValueError, TypeError):
        return None


def attendance_json(item):
    return {
        "id": item.id,
        "user_id": item.user_id,
        "username": item.user.username,
        "date": item.work_date.isoformat(),
        "check_in": item.check_in.isoformat() if item.check_in else None,
        "check_out": item.check_out.isoformat() if item.check_out else None,
        "status": item.status,
        "note": item.note,
    }


def leave_json(item):
    return {
        "id": item.id,
        "username": item.user.username,
        "leave_type": item.leave_type,
        "start_date": item.start_date.isoformat(),
        "end_date": item.end_date.isoformat(),
        "reason": item.reason,
        "status": item.status,
        "created_at": item.created_at.isoformat(),
    }


@attendance_api.post("/companies/<int:cid>/attendance/check-in")
@login_required
def check_in(cid):
    if not active_member(cid, current_user.id):
        return error("Active company membership required", 403)

    today = date.today()
    item = Attendance.query.filter_by(
        company_id=cid, user_id=current_user.id, work_date=today
    ).first()

    if item and item.check_in:
        return error("Already checked in today", 409)

    if not item:
        item = Attendance(
            company_id=cid, user_id=current_user.id, work_date=today
        )
        db.session.add(item)

    item.check_in = datetime.now(timezone.utc)
    item.status = "present"
    db.session.flush()
    log_company_activity(
        cid, "attendance_check_in", "attendance", item.id,
        {"date": today.isoformat()},
    )
    db.session.commit()

    return jsonify({"ok": True, "attendance": attendance_json(item)})


@attendance_api.post("/companies/<int:cid>/attendance/check-out")
@login_required
def check_out(cid):
    if not active_member(cid, current_user.id):
        return error("Active company membership required", 403)

    item = Attendance.query.filter_by(
        company_id=cid, user_id=current_user.id, work_date=date.today()
    ).first()

    if not item or not item.check_in:
        return error("Check in before checking out")

    if item.check_out:
        return error("Already checked out today", 409)

    item.check_out = datetime.now(timezone.utc)
    log_company_activity(
        cid, "attendance_check_out", "attendance", item.id,
        {"date": item.work_date.isoformat()},
    )
    db.session.commit()

    return jsonify({"ok": True, "attendance": attendance_json(item)})


@attendance_api.get("/companies/<int:cid>/attendance")
@login_required
def attendance_list(cid):
    if not active_member(cid, current_user.id):
        return error("Active company membership required", 403)

    query = Attendance.query.filter_by(company_id=cid)

    start = request.args.get("start")
    end = request.args.get("end")
    user_id = request.args.get("user_id")

    if start:
        day = parse_day(start)
        if not day:
            return error("Invalid start date; use YYYY-MM-DD")
        query = query.filter(Attendance.work_date >= day)

    if end:
        day = parse_day(end)
        if not day:
            return error("Invalid end date; use YYYY-MM-DD")
        query = query.filter(Attendance.work_date <= day)

    if user_id:
        if not can_manage_company(cid, current_user.id):
            return error("HR/Admin permission required", 403)
        try:
            query = query.filter(Attendance.user_id == int(user_id))
        except ValueError:
            return error("Invalid user_id")

    items = query.order_by(Attendance.work_date.desc()).limit(500).all()

    return jsonify({
        "ok": True,
        "attendance": [attendance_json(x) for x in items]
    })


@attendance_api.post("/companies/<int:cid>/leaves")
@login_required
def apply_leave(cid):
    if not active_member(cid, current_user.id):
        return error("Active company membership required", 403)

    data = request.get_json(silent=True) or request.form
    start = parse_day(data.get("start_date"))
    end = parse_day(data.get("end_date"))
    reason = str(data.get("reason", "")).strip()
    leave_type = str(data.get("leave_type", "casual")).strip().lower()

    if not start or not end or end < start:
        return error("Valid start_date and end_date are required")

    if not reason or len(reason) > 1000:
        return error("Reason is required (maximum 1000 characters)")

    if leave_type not in ("casual", "sick", "annual", "unpaid", "other"):
        return error("Invalid leave type")

    item = LeaveRequest(
        company_id=cid,
        user_id=current_user.id,
        leave_type=leave_type,
        start_date=start,
        end_date=end,
        reason=reason,
    )
    db.session.add(item)
    db.session.flush()

    log_company_activity(
        cid, "leave_requested", "leave_request", item.id,
        {
            "leave_type": leave_type,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
    )

    company = Company.query.filter_by(id=cid).first()
    recipient_ids = set()
    if company:
        recipient_ids.add(company.owner_id)

    managers = CompanyEmployee.query.filter(
        CompanyEmployee.company_id == cid,
        CompanyEmployee.status == "active",
        CompanyEmployee.role.in_(("owner", "admin", "hr")),
        CompanyEmployee.user_id != current_user.id,
    ).all()
    recipient_ids.update(member.user_id for member in managers)
    recipient_ids.discard(current_user.id)

    for recipient_id in recipient_ids:
        add_notification(
            recipient_id,
            "New leave request",
            f"{current_user.username} requested {leave_type} leave "
            f"from {start.isoformat()} to {end.isoformat()}",
            kind="leave_requested",
            actor_id=current_user.id,
            object_type="leave_request",
            object_id=item.id,
        )

    db.session.commit()
    return jsonify({"ok": True, "leave": leave_json(item)}), 201


@attendance_api.get("/companies/<int:cid>/leaves")
@login_required
def list_leaves(cid):
    if not active_member(cid, current_user.id):
        return error("Active company membership required", 403)

    query = LeaveRequest.query.filter_by(company_id=cid)

    if not can_manage_company(cid, current_user.id):
        query = query.filter_by(user_id=current_user.id)

    status = request.args.get("status")
    if status:
        if status not in ("pending", "approved", "rejected", "cancelled"):
            return error("Invalid leave status")
        query = query.filter_by(status=status)

    items = query.order_by(LeaveRequest.created_at.desc()).limit(300).all()

    return jsonify({"ok": True, "leaves": [leave_json(x) for x in items]})


@attendance_api.post("/companies/<int:cid>/leaves/<int:leave_id>/review")
@login_required
def review_leave(cid, leave_id):
    if not can_manage_company(cid, current_user.id):
        return error("HR/Admin permission required", 403)

    item = LeaveRequest.query.filter_by(
        id=leave_id, company_id=cid
    ).first_or_404()

    data = request.get_json(silent=True) or request.form
    decision = str(data.get("status", "")).strip().lower()

    if decision not in ("approved", "rejected"):
        return error("Status must be approved or rejected")

    if item.status != "pending":
        return error("Only pending requests can be reviewed", 409)

    item.status = decision
    item.reviewed_by_id = current_user.id
    item.reviewed_at = datetime.now(timezone.utc)

    log_company_activity(
        cid, "leave_reviewed", "leave_request", item.id,
        {"status": decision, "leave_type": item.leave_type},
    )
    add_notification(
        item.user_id,
        "Leave request reviewed",
        f"Your {item.leave_type} leave request was {decision}.",
        kind="leave_reviewed",
        actor_id=current_user.id,
        object_type="leave_request",
        object_id=item.id,
    )
    db.session.commit()

    return jsonify({"ok": True, "leave": leave_json(item)})


@attendance_api.post("/companies/<int:cid>/leaves/<int:leave_id>/cancel")
@login_required
def cancel_leave(cid, leave_id):
    item = LeaveRequest.query.filter_by(
        id=leave_id, company_id=cid, user_id=current_user.id
    ).first_or_404()

    if item.status != "pending":
        return error("Only pending requests can be cancelled", 409)

    item.status = "cancelled"
    log_company_activity(
        cid, "leave_cancelled", "leave_request", item.id,
        {"leave_type": item.leave_type},
    )
    db.session.commit()

    return jsonify({"ok": True, "status": item.status})
