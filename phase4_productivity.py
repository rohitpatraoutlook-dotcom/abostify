from datetime import date, datetime, timezone

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from models import db
from extended_models import Workspace, WorkspaceMembership, Team, TeamMembership
from company_portal import Company, CompanyEmployee

phase4 = Blueprint("phase4", __name__, url_prefix="/api/v4")


class ProductivityItem(db.Model):
    __tablename__ = "phase4_productivity_item"

    id = db.Column(db.Integer, primary_key=True)
    scope = db.Column(db.String(20), nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False, default="task")
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    workspace_id = db.Column(db.Integer, db.ForeignKey("workspace.id"), index=True)
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"), index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), nullable=False, default="todo")
    priority = db.Column(db.String(20), nullable=False, default="medium")
    due_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))


def fail(message, status=400):
    return jsonify({"ok": False, "error": message}), status


def workspace_member(workspace_id, user_id):
    return WorkspaceMembership.query.filter_by(
        workspace_id=workspace_id, user_id=user_id, status="active"
    ).first()


def team_member(team_id, user_id):
    return TeamMembership.query.filter_by(team_id=team_id, user_id=user_id).first()


def active_company_for_workspace(workspace_id):
    return Company.query.filter_by(workspace_id=workspace_id, is_active=True).first()


def can_manage_workspace(workspace_id, user_id):
    member = workspace_member(workspace_id, user_id)
    return bool(member and member.role in ("owner", "admin", "manager"))


def can_access_item(item, user_id):
    if item.scope == "individual":
        return item.owner_id == user_id
    if item.scope == "company":
        return bool(item.workspace_id and workspace_member(item.workspace_id, user_id))
    if item.scope == "team":
        return bool(item.team_id and team_member(item.team_id, user_id))
    return False


def serialize(item):
    return {
        "id": item.id, "scope": item.scope, "kind": item.kind,
        "title": item.title, "description": item.description or "",
        "status": item.status, "priority": item.priority,
        "due_date": item.due_date.isoformat() if item.due_date else "",
        "owner_id": item.owner_id, "created_by_id": item.created_by_id,
        "workspace_id": item.workspace_id, "team_id": item.team_id,
        "created_at": item.created_at.isoformat(),
    }


@phase4.get("/workspaces")
@login_required
def list_workspaces():
    memberships = WorkspaceMembership.query.filter_by(
        user_id=current_user.id, status="active"
    ).all()
    result = []
    for membership in memberships:
        workspace = db.session.get(Workspace, membership.workspace_id)
        if workspace and not workspace.is_archived:
            company = active_company_for_workspace(workspace.id)
            result.append({
                "id": workspace.id,
                "name": company.name if company else workspace.name,
                "role": membership.role,
                "company_id": company.id if company else None,
            })
    return jsonify({"items": result})


@phase4.get("/teams")
@login_required
def list_teams():
    workspace_id = request.args.get("workspace_id", type=int)
    if workspace_id:
        if not workspace_member(workspace_id, current_user.id):
            return fail("Company workspace membership required.", 403)
        teams = Team.query.filter_by(workspace_id=workspace_id).order_by(Team.name).all()
    else:
        memberships = TeamMembership.query.filter_by(user_id=current_user.id).all()
        ids = [m.team_id for m in memberships]
        teams = Team.query.filter(Team.id.in_(ids)).order_by(Team.name).all() if ids else []

    return jsonify({"items": [
        {"id": t.id, "name": t.name, "description": t.description or "",
         "workspace_id": t.workspace_id,
         "member_count": TeamMembership.query.filter_by(team_id=t.id).count(),
         "is_member": bool(team_member(t.id, current_user.id))}
        for t in teams
    ]})


@phase4.post("/teams")
@login_required
def create_team():
    data = request.get_json(silent=True) or {}
    workspace_id = data.get("workspace_id")
    name = str(data.get("name", "")).strip()
    if not isinstance(workspace_id, int):
        return fail("Choose a company workspace first.")
    workspace = db.session.get(Workspace, workspace_id)
    if not workspace or workspace.is_archived or not active_company_for_workspace(workspace_id):
        return fail("Teams must be connected to an active company.", 400)
    if not can_manage_workspace(workspace_id, current_user.id):
        return fail("Company owner, admin or manager permission required.", 403)
    if not name or len(name) > 120:
        return fail("Team name is required (maximum 120 characters).")

    team = Team(workspace_id=workspace_id, name=name,
                description=str(data.get("description", "")).strip() or None)
    db.session.add(team)
    db.session.flush()
    db.session.add(TeamMembership(team_id=team.id, user_id=current_user.id, role="lead"))
    db.session.commit()
    return jsonify({"ok": True, "item": {
        "id": team.id, "name": team.name, "workspace_id": workspace_id
    }}), 201


@phase4.post("/teams/<int:team_id>/members")
@login_required
def add_team_member(team_id):
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    team = db.session.get(Team, team_id)
    if not team:
        return fail("Team not found.", 404)
    if not can_manage_workspace(team.workspace_id, current_user.id):
        return fail("Company manager permission required.", 403)
    if not isinstance(user_id, int):
        return fail("A valid employee user_id is required.")

    employee = CompanyEmployee.query.filter_by(
        user_id=user_id, status="active"
    ).first()
    if not employee:
        return fail("User must be an active company employee.", 400)
    company = active_company_for_workspace(team.workspace_id)
    if not company or employee.company_id != company.id:
        return fail("Team members must belong to the same company.", 403)
    if team_member(team_id, user_id):
        return fail("User is already a team member.", 409)

    db.session.add(TeamMembership(team_id=team_id, user_id=user_id, role="member"))
    db.session.commit()
    return jsonify({"ok": True}), 201


@phase4.route("/productivity/items", methods=["GET", "POST"])
@login_required
def productivity_items():
    if request.method == "GET":
        scope = request.args.get("scope", "individual")
        query = ProductivityItem.query.filter_by(scope=scope)

        if scope == "individual":
            query = query.filter_by(owner_id=current_user.id)
        elif scope == "company":
            workspace_id = request.args.get("workspace_id", type=int)
            if not workspace_id or not workspace_member(workspace_id, current_user.id):
                return fail("Company workspace membership required.", 403)
            query = query.filter_by(workspace_id=workspace_id)
        elif scope == "team":
            team_id = request.args.get("team_id", type=int)
            if not team_id or not team_member(team_id, current_user.id):
                return fail("Team membership required.", 403)
            query = query.filter_by(team_id=team_id)
        else:
            return fail("Invalid scope.")

        items = query.order_by(ProductivityItem.created_at.desc()).limit(300).all()
        return jsonify({"items": [serialize(i) for i in items]})

    data = request.get_json(silent=True) or {}
    scope = data.get("scope", "individual")
    kind = data.get("kind", "task")
    title = str(data.get("title", "")).strip()
    if scope not in ("individual", "company", "team"):
        return fail("Invalid scope.")
    if kind not in ("task", "goal", "note"):
        return fail("Kind must be task, goal or note.")
    if not title or len(title) > 200:
        return fail("Title is required (maximum 200 characters).")

    workspace_id = team_id = None
    if scope == "company":
        workspace_id = data.get("workspace_id")
        if not isinstance(workspace_id, int) or not workspace_member(workspace_id, current_user.id):
            return fail("Company workspace membership required.", 403)
        if not active_company_for_workspace(workspace_id):
            return fail("Active company required.", 403)
    elif scope == "team":
        team_id = data.get("team_id")
        team = db.session.get(Team, team_id) if isinstance(team_id, int) else None
        if not team or not team_member(team.id, current_user.id):
            return fail("Team membership required.", 403)
        workspace_id = team.workspace_id

    due_date = None
    if data.get("due_date"):
        try:
            due_date = date.fromisoformat(str(data["due_date"]))
        except ValueError:
            return fail("Due date must use YYYY-MM-DD.")

    status = data.get("status", "todo")
    priority = data.get("priority", "medium")
    if status not in ("todo", "in_progress", "completed", "blocked"):
        return fail("Invalid status.")
    if priority not in ("low", "medium", "high", "urgent"):
        return fail("Invalid priority.")

    item = ProductivityItem(
        scope=scope, kind=kind, owner_id=current_user.id,
        created_by_id=current_user.id, workspace_id=workspace_id, team_id=team_id,
        title=title, description=str(data.get("description", ""))[:10000] or None,
        status=status, priority=priority, due_date=due_date
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({"ok": True, "item": serialize(item)}), 201


@phase4.route("/productivity/items/<int:item_id>", methods=["PATCH", "DELETE"])
@login_required
def productivity_item_detail(item_id):
    item = db.session.get(ProductivityItem, item_id)
    if not item:
        return fail("Item not found.", 404)
    if not can_access_item(item, current_user.id):
        return fail("You do not have access to this item.", 403)

    if request.method == "DELETE":
        if item.created_by_id != current_user.id and item.scope != "individual":
            return fail("Only the creator can delete this shared item.", 403)
        db.session.delete(item)
        db.session.commit()
        return jsonify({"ok": True})

    data = request.get_json(silent=True) or {}
    if "title" in data:
        title = str(data["title"]).strip()
        if not title or len(title) > 200:
            return fail("Title is required (maximum 200 characters).")
        item.title = title
    if "description" in data:
        item.description = str(data["description"])[:10000] or None
    if "status" in data:
        if data["status"] not in ("todo", "in_progress", "completed", "blocked"):
            return fail("Invalid status.")
        item.status = data["status"]
    if "priority" in data:
        if data["priority"] not in ("low", "medium", "high", "urgent"):
            return fail("Invalid priority.")
        item.priority = data["priority"]
    db.session.commit()
    return jsonify({"ok": True, "item": serialize(item)})
