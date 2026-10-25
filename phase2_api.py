from datetime import datetime, timezone, date
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError

from models import db, User
from phase2_events import record_activity, add_notification

from company_portal import (
    Company, CompanyEmployee, can_manage_company
)

phase2 = Blueprint("phase2", __name__, url_prefix="/api/v2")


def fail(message, status=400):
    return jsonify({"ok": False, "error": message}), status


def employee(company_id, user_id):
    return CompanyEmployee.query.filter_by(
        company_id=company_id,
        user_id=user_id,
        status="active"
    ).first()


def manager(company_id):
    if not can_manage_company(company_id, current_user.id):
        return None
    return Company.query.get(company_id)


def log_employee_event(company, action, record, details=None):
    record_activity(
        workspace_id=company.workspace_id,
        actor_id=current_user.id,
        action=action,
        object_type="company_employee",
        object_id=record.id,
        details=details or {},
        ip_address=request.remote_addr,
    )


def notify_employee(record, title, body, kind):
    if record.user_id != current_user.id:
        add_notification(
            record.user_id, title, body, kind=kind,
            actor_id=current_user.id,
            object_type="company_employee",
            object_id=record.id,
        )


@phase2.get("/companies/<int:company_id>/employees")
@login_required
def employees_list(company_id):
    company = Company.query.get_or_404(company_id)

    if not employee(company_id, current_user.id):
        return fail("Active company membership required", 403)

    records = CompanyEmployee.query.filter_by(
        company_id=company.id
    ).order_by(CompanyEmployee.joined_at.desc()).all()

    return jsonify({
        "ok": True,
        "employees": [{
            "id": item.id,
            "user_id": item.user_id,
            "username": item.user.username,
            "display_name": item.user.display_name or item.user.username,
            "email": item.user.email,
            "role": item.role,
            "designation": item.designation,
            "department": item.department,
            "status": item.status,
            "joined_at": item.joined_at.isoformat()
        } for item in records]
    })


@phase2.post("/companies/<int:company_id>/employees")
@login_required
def add_employee(company_id):
    company = manager(company_id)

    if not company:
        return fail("HR/Admin permission required", 403)

    data = request.get_json(silent=True) or request.form
    username = str(data.get("username", "")).strip()
    designation = str(data.get("designation", "")).strip()[:100]
    department = str(data.get("department", "")).strip()[:100]

    if not username:
        return fail("Username is required")

    user = User.query.filter_by(username=username).first()
    if not user:
        return fail("User not found", 404)

    existing = CompanyEmployee.query.filter_by(
        company_id=company.id,
        user_id=user.id
    ).first()

    if existing:
        if existing.status == "active":
            return fail("User is already an active employee", 409)
        existing.status = "active"
        existing.designation = designation or existing.designation
        existing.department = department or existing.department
        log_employee_event(company, "employee_reactivated", existing)
        notify_employee(
            existing, "Company access restored",
            f"Your membership at {company.name} is active again.",
            "employee_reactivated",
        )
        db.session.commit()
        return jsonify({"ok": True, "message": "Employee reactivated"})

    record = CompanyEmployee(
        company_id=company.id,
        user_id=user.id,
        role="employee",
        designation=designation or None,
        department=department or None,
        status="active"
    )
    db.session.add(record)

    try:
        db.session.flush()
        log_employee_event(company, "employee_added", record)
        notify_employee(
            record, "Added to company",
            f"You have been added to {company.name}.", "employee_added",
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return fail("Employee could not be added", 409)

    return jsonify({
        "ok": True,
        "message": "Employee added",
        "employee_id": record.id
    }), 201


@phase2.patch("/companies/<int:company_id>/employees/<int:employee_id>")
@login_required
def update_employee(company_id, employee_id):
    if not manager(company_id):
        return fail("HR/Admin permission required", 403)

    record = CompanyEmployee.query.filter_by(
        id=employee_id,
        company_id=company_id
    ).first_or_404()

    data = request.get_json(silent=True) or request.form

    if "designation" in data:
        record.designation = str(data["designation"]).strip()[:100] or None

    if "department" in data:
        record.department = str(data["department"]).strip()[:100] or None

    if "reporting_manager_id" in data:
        value = data["reporting_manager_id"]
        if value in ("", None, 0, "0"):
            record.reporting_manager_id = None
        else:
            try:
                manager_id = int(value)
            except (ValueError, TypeError):
                return fail("Invalid reporting manager ID")

            if not employee(company_id, manager_id):
                return fail("Reporting manager must be an active employee")
            record.reporting_manager_id = manager_id

    company = Company.query.get(company_id)
    log_employee_event(
        company, "employee_updated", record,
        {
            "designation": record.designation,
            "department": record.department,
            "reporting_manager_id": record.reporting_manager_id,
        },
    )
    db.session.commit()
    return jsonify({"ok": True, "message": "Employee updated"})


@phase2.post("/companies/<int:company_id>/employees/<int:employee_id>/status")
@login_required
def employee_status(company_id, employee_id):
    if not manager(company_id):
        return fail("HR/Admin permission required", 403)

    record = CompanyEmployee.query.filter_by(
        id=employee_id,
        company_id=company_id
    ).first_or_404()

    if record.role == "owner":
        return fail("Company owner cannot be suspended here", 403)

    data = request.get_json(silent=True) or request.form
    status = str(data.get("status", "")).strip().lower()

    if status not in ("active", "suspended"):
        return fail("Status must be active or suspended")

    record.status = status
    company = Company.query.get(company_id)
    log_employee_event(
        company, "employee_status_changed", record, {"status": status}
    )
    notify_employee(
        record, "Company access updated",
        f"Your membership status at {company.name} is now {status}.",
        "employee_status_changed",
    )
    db.session.commit()

    return jsonify({"ok": True, "status": record.status})


@phase2.get("/companies/<int:company_id>/summary")
@login_required
def company_summary(company_id):
    company = Company.query.get_or_404(company_id)

    if not employee(company_id, current_user.id):
        return fail("Active company membership required", 403)

    records = CompanyEmployee.query.filter_by(
        company_id=company_id
    ).all()

    return jsonify({
        "ok": True,
        "company": company.name,
        "total_employees": len(records),
        "active_employees": sum(x.status == "active" for x in records),
        "suspended_employees": sum(x.status == "suspended" for x in records)
    })
