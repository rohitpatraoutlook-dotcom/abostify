import re
from datetime import datetime, timezone

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, abort
)
from flask_login import current_user, login_required
from sqlalchemy import UniqueConstraint, CheckConstraint, or_
from sqlalchemy.exc import IntegrityError

from models import db, User
from extended_models import Workspace, WorkspaceMembership

company_portal = Blueprint("company_portal", __name__)


def now_utc():
    return datetime.now(timezone.utc)


class Company(db.Model):
    __tablename__ = "company"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, index=True)
    slug = db.Column(db.String(160), unique=True, nullable=False, index=True)
    industry = db.Column(db.String(100))
    website = db.Column(db.String(250))
    location = db.Column(db.String(150))
    description = db.Column(db.Text)
    owner_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    workspace_id = db.Column(
        db.Integer, db.ForeignKey("workspace.id", ondelete="RESTRICT"),
        unique=True, nullable=False
    )
    created_at = db.Column(db.DateTime(timezone=True), default=now_utc, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    owner = db.relationship("User", foreign_keys=[owner_id])
    workspace = db.relationship("Workspace", foreign_keys=[workspace_id])
    employees = db.relationship(
        "CompanyEmployee", back_populates="company",
        cascade="all, delete-orphan"
    )
    join_requests = db.relationship(
        "CompanyJoinRequest", back_populates="company",
        cascade="all, delete-orphan"
    )


class CompanyEmployee(db.Model):
    __tablename__ = "company_employee"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(
        db.Integer, db.ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # Permission role is separate from designation.
    role = db.Column(db.String(20), default="employee", nullable=False)
    designation = db.Column(db.String(100))
    department = db.Column(db.String(100))
    reporting_manager_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="SET NULL")
    )
    status = db.Column(db.String(20), default="active", nullable=False)
    joined_at = db.Column(db.DateTime(timezone=True), default=now_utc, nullable=False)

    __table_args__ = (
        UniqueConstraint("company_id", "user_id", name="uq_company_employee"),
        CheckConstraint(
            "role IN ('owner', 'admin', 'hr', 'manager', 'employee')",
            name="ck_company_employee_role"
        ),
        CheckConstraint(
            "status IN ('active', 'suspended')",
            name="ck_company_employee_status"
        ),
    )

    company = db.relationship("Company", back_populates="employees")
    user = db.relationship("User", foreign_keys=[user_id])
    reporting_manager = db.relationship("User", foreign_keys=[reporting_manager_id])


class CompanyJoinRequest(db.Model):
    __tablename__ = "company_join_request"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(
        db.Integer, db.ForeignKey("company.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    message = db.Column(db.String(1000))
    status = db.Column(db.String(20), default="pending", nullable=False, index=True)
    requested_at = db.Column(db.DateTime(timezone=True), default=now_utc, nullable=False)
    reviewed_at = db.Column(db.DateTime(timezone=True))
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"))

    __table_args__ = (
        UniqueConstraint("company_id", "user_id", name="uq_company_join_request"),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_company_join_request_status"
        ),
    )

    company = db.relationship("Company", back_populates="join_requests")
    user = db.relationship("User", foreign_keys=[user_id])
    reviewed_by = db.relationship("User", foreign_keys=[reviewed_by_id])


def employee_record(company_id, user_id):
    return CompanyEmployee.query.filter_by(
        company_id=company_id, user_id=user_id, status="active"
    ).first()


def can_manage_company(company_id, user_id):
    employee = employee_record(company_id, user_id)
    return bool(employee and employee.role in ("owner", "admin", "hr"))


def company_slug(name):
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:140]
    if not base:
        return None
    slug = base
    suffix = 2
    while Company.query.filter_by(slug=slug).first():
        slug = f"{base[:130]}-{suffix}"
        suffix += 1
    return slug


def company_page_data(company):
    members = []
    pending_requests = []
    my_employee = None

    if company:
        my_employee = employee_record(company.id, current_user.id)
        if my_employee:
            # Include suspended employees so authorized admins can reactivate them.
            members = (
                CompanyEmployee.query
                .filter_by(company_id=company.id)
                .order_by(CompanyEmployee.joined_at.asc())
                .all()
            )
        if can_manage_company(company.id, current_user.id):
            pending_requests = (
                CompanyJoinRequest.query
                .filter_by(company_id=company.id, status="pending")
                .order_by(CompanyJoinRequest.requested_at.asc())
                .all()
            )

    my_companies = (
        Company.query.join(
            CompanyEmployee, CompanyEmployee.company_id == Company.id
        )
        .filter(
            CompanyEmployee.user_id == current_user.id,
            CompanyEmployee.status == "active",
            Company.is_active.is_(True),
        )
        .order_by(Company.name.asc())
        .all()
    )

    query = request.args.get("q", "").strip()[:100]
    search_query = Company.query.filter_by(is_active=True)
    if query:
        search_query = search_query.filter(
            or_(
                Company.name.ilike(f"%{query}%"),
                Company.industry.ilike(f"%{query}%"),
                Company.location.ilike(f"%{query}%"),
            )
        )
    companies = search_query.order_by(Company.name.asc()).limit(100).all()

    request_by_company = {
        item.company_id: item
        for item in CompanyJoinRequest.query.filter_by(user_id=current_user.id).all()
    }
    employee_company_ids = {
        item.company_id for item in CompanyEmployee.query.filter_by(
            user_id=current_user.id, status="active"
        ).all()
    }

    return dict(
        company=company,
        members=members,
        pending_requests=pending_requests,
        my_employee=my_employee,
        can_manage=bool(
            company and can_manage_company(company.id, current_user.id)
        ),
        my_companies=my_companies,
        companies=companies,
        request_by_company=request_by_company,
        employee_company_ids=employee_company_ids,
        search_query=query,
    )


@company_portal.get("/companies")
@login_required
def companies_home():
    return render_template(
        "companies.html",
        **company_page_data(None),
    )


@company_portal.post("/companies/register")
@login_required
def register_company():
    name = request.form.get("name", "").strip()
    industry = request.form.get("industry", "").strip()[:100]
    website = request.form.get("website", "").strip()[:250]
    location = request.form.get("location", "").strip()[:150]
    description = request.form.get("description", "").strip()

    if not 3 <= len(name) <= 150:
        flash("Company name must contain 3–150 characters.", "error")
        return redirect(url_for("company_portal.companies_home"))

    if len(description) > 5000:
        flash("Description must be 5,000 characters or fewer.", "error")
        return redirect(url_for("company_portal.companies_home"))

    slug = company_slug(name)
    if not slug:
        flash("Company name must contain letters or numbers.", "error")
        return redirect(url_for("company_portal.companies_home"))

    try:
        workspace = Workspace(
            name=name,
            slug=f"company-{slug}"[:160],
            description=description[:3000],
            owner_id=current_user.id,
            is_archived=False,
        )
        # Keep the workspace slug unique even if a personal workspace has the same name.
        base_workspace_slug = workspace.slug[:140]
        suffix = 2
        while Workspace.query.filter_by(slug=workspace.slug).first():
            workspace.slug = f"{base_workspace_slug}-{suffix}"[:160]
            suffix += 1

        db.session.add(workspace)
        db.session.flush()

        membership = WorkspaceMembership(
            workspace_id=workspace.id,
            user_id=current_user.id,
            role="owner",
            status="active",
        )
        db.session.add(membership)

        company = Company(
            name=name,
            slug=slug,
            industry=industry or None,
            website=website or None,
            location=location or None,
            description=description or None,
            owner_id=current_user.id,
            workspace_id=workspace.id,
        )
        db.session.add(company)
        db.session.flush()

        db.session.add(CompanyEmployee(
            company_id=company.id,
            user_id=current_user.id,
            role="owner",
            designation="Company Owner",
            department="Management",
            status="active",
        ))
        db.session.commit()
        flash("Company created successfully. You are the owner.", "success")
        return redirect(url_for("company_portal.company_detail", slug=company.slug))

    except IntegrityError:
        db.session.rollback()
        flash("Could not create this company due to a conflicting record. Try again.", "error")
        return redirect(url_for("company_portal.companies_home"))


@company_portal.get("/companies/<string:slug>")
@login_required
def company_detail(slug):
    company = Company.query.filter_by(slug=slug, is_active=True).first_or_404()
    return render_template("companies.html", **company_page_data(company))


@company_portal.post("/companies/<int:company_id>/join")
@login_required
def request_to_join(company_id):
    company = db.session.get(Company, company_id)
    if not company or not company.is_active:
        abort(404)

    if employee_record(company.id, current_user.id):
        flash("You are already a member of this company.", "info")
        return redirect(url_for("company_portal.company_detail", slug=company.slug))

    message = request.form.get("message", "").strip()
    if len(message) > 1000:
        flash("Join message must be 1,000 characters or fewer.", "error")
        return redirect(url_for("company_portal.company_detail", slug=company.slug))

    existing = CompanyJoinRequest.query.filter_by(
        company_id=company.id, user_id=current_user.id
    ).first()

    if existing and existing.status == "pending":
        flash("Your join request is already pending.", "info")
    else:
        if existing:
            existing.status = "pending"
            existing.message = message or None
            existing.requested_at = now_utc()
            existing.reviewed_at = None
            existing.reviewed_by_id = None
        else:
            db.session.add(CompanyJoinRequest(
                company_id=company.id,
                user_id=current_user.id,
                message=message or None,
                status="pending",
            ))
        db.session.commit()
        flash("Join request sent to company HR/owner.", "success")

    return redirect(url_for("company_portal.company_detail", slug=company.slug))


@company_portal.post("/companies/<int:company_id>/requests/<int:request_id>/review")
@login_required
def review_join_request(company_id, request_id):
    company = db.session.get(Company, company_id)
    if not company or not company.is_active:
        abort(404)

    if not can_manage_company(company.id, current_user.id):
        abort(403)

    join_request = CompanyJoinRequest.query.filter_by(
        id=request_id, company_id=company.id, status="pending"
    ).first_or_404()

    decision = request.form.get("decision", "").strip().lower()
    if decision not in ("approve", "reject"):
        flash("Invalid review action.", "error")
        return redirect(url_for("company_portal.company_detail", slug=company.slug))

    if decision == "reject":
        join_request.status = "rejected"
        join_request.reviewed_at = now_utc()
        join_request.reviewed_by_id = current_user.id
        db.session.commit()
        flash("Join request rejected.", "success")
        return redirect(url_for("company_portal.company_detail", slug=company.slug))

    if employee_record(company.id, join_request.user_id):
        join_request.status = "approved"
        join_request.reviewed_at = now_utc()
        join_request.reviewed_by_id = current_user.id
        db.session.commit()
        flash("This user is already a company member.", "info")
        return redirect(url_for("company_portal.company_detail", slug=company.slug))

    role = request.form.get("role", "employee").strip().lower()
    allowed_roles = {"admin", "hr", "manager", "employee"}
    if role not in allowed_roles:
        role = "employee"

    department = request.form.get("department", "").strip()[:100] or None
    designation = request.form.get("designation", "").strip()[:100] or None
    manager_raw = request.form.get("reporting_manager_id", "").strip()
    manager_id = None

    if manager_raw:
        try:
            candidate_id = int(manager_raw)
            if employee_record(company.id, candidate_id):
                manager_id = candidate_id
            else:
                flash("Reporting manager must be an active employee of this company.", "error")
                return redirect(url_for("company_portal.company_detail", slug=company.slug))
        except ValueError:
            flash("Invalid reporting manager.", "error")
            return redirect(url_for("company_portal.company_detail", slug=company.slug))

    try:
        db.session.add(CompanyEmployee(
            company_id=company.id,
            user_id=join_request.user_id,
            role=role,
            department=department,
            designation=designation,
            reporting_manager_id=manager_id,
            status="active",
        ))

        workspace_role = "manager" if role == "manager" else "member"
        workspace_membership = WorkspaceMembership.query.filter_by(
            workspace_id=company.workspace_id,
            user_id=join_request.user_id,
        ).first()

        if workspace_membership:
            workspace_membership.status = "active"
            workspace_membership.role = workspace_role
        else:
            db.session.add(WorkspaceMembership(
                workspace_id=company.workspace_id,
                user_id=join_request.user_id,
                role=workspace_role,
                status="active",
            ))

        join_request.status = "approved"
        join_request.reviewed_at = now_utc()
        join_request.reviewed_by_id = current_user.id
        db.session.commit()
        flash("Employee approved and added to the company.", "success")

    except IntegrityError:
        db.session.rollback()
        flash("Could not approve this request because of a conflicting membership.", "error")

    return redirect(url_for("company_portal.company_detail", slug=company.slug))


@company_portal.post("/companies/<int:company_id>/employees/<int:employee_id>/edit")
@login_required
def edit_company_employee(company_id, employee_id):
    company = db.session.get(Company, company_id)
    if not company or not company.is_active:
        abort(404)

    actor = employee_record(company_id, current_user.id)
    if not actor or actor.role not in ("owner", "admin", "hr"):
        abort(403)

    target = CompanyEmployee.query.filter_by(
        id=employee_id, company_id=company_id
    ).first_or_404()

    if target.role == "owner":
        abort(403)

    if actor.role == "hr" and target.role in ("owner", "admin", "hr"):
        abort(403)

    role = request.form.get("role", "employee").strip().lower()
    allowed_roles = {"employee", "manager", "hr", "admin"}

    if role not in allowed_roles:
        flash("Invalid employee role.", "error")
        return redirect(url_for(
            "company_portal.company_detail", slug=company.slug
        ))

    # HR cannot grant HR/admin privileges or edit privileged employees.
    if actor.role == "hr":
        if role not in {"employee", "manager"}:
            abort(403)

    if target.user_id == current_user.id and role != target.role:
        flash("You cannot change your own permission role here.", "error")
        return redirect(url_for(
            "company_portal.company_detail", slug=company.slug
        ))

    manager_raw = request.form.get("reporting_manager_id", "").strip()
    manager_id = None

    if manager_raw:
        try:
            manager_id = int(manager_raw)
        except ValueError:
            flash("Invalid reporting manager.", "error")
            return redirect(url_for(
                "company_portal.company_detail", slug=company.slug
            ))

        if manager_id == target.user_id or not employee_record(
            company_id, manager_id
        ):
            flash("Choose another active employee as reporting manager.", "error")
            return redirect(url_for(
                "company_portal.company_detail", slug=company.slug
            ))

    target.role = role
    target.designation = request.form.get("designation", "").strip()[:100] or None
    target.department = request.form.get("department", "").strip()[:100] or None
    target.reporting_manager_id = manager_id

    membership = WorkspaceMembership.query.filter_by(
        workspace_id=company.workspace_id,
        user_id=target.user_id,
    ).first()

    if membership and target.status == "active":
        membership.role = "manager" if role == "manager" else "member"
        membership.status = "active"

    db.session.commit()
    flash("Employee details updated.", "success")
    return redirect(url_for(
        "company_portal.company_detail", slug=company.slug
    ))


@company_portal.post("/companies/<int:company_id>/employees/<int:employee_id>/status")
@login_required
def change_company_employee_status(company_id, employee_id):
    company = db.session.get(Company, company_id)
    if not company or not company.is_active:
        abort(404)

    actor = employee_record(company_id, current_user.id)
    if not actor or actor.role not in ("owner", "admin", "hr"):
        abort(403)

    target = CompanyEmployee.query.filter_by(
        id=employee_id, company_id=company_id
    ).first_or_404()

    if target.role == "owner" or target.user_id == current_user.id:
        abort(403)

    if actor.role == "hr" and target.role in ("owner", "admin", "hr"):
        abort(403)

    new_status = request.form.get("status", "").strip().lower()
    if new_status not in {"active", "suspended"}:
        abort(400)

    target.status = new_status

    membership = WorkspaceMembership.query.filter_by(
        workspace_id=company.workspace_id,
        user_id=target.user_id,
    ).first()

    if membership:
        membership.status = new_status

    db.session.commit()
    flash(
        "Employee reactivated." if new_status == "active"
        else "Employee suspended.",
        "success",
    )
    return redirect(url_for(
        "company_portal.company_detail", slug=company.slug
    ))
