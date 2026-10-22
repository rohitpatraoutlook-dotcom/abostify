import re
from datetime import date, datetime, timezone

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from models import db, User
from extended_models import (
    Workspace, WorkspaceMembership,
    Team, TeamMembership,
    Project, ProjectMembership,
    Task, FileAsset,
)

business_api = Blueprint("business_api", __name__, url_prefix="/api")


def error(message, status=400):
    return jsonify({"error": message}), status


def get_membership(workspace_id, user_id):
    return WorkspaceMembership.query.filter_by(
        workspace_id=workspace_id,
        user_id=user_id,
        status="active",
    ).first()


def has_role(workspace_id, user_id, roles):
    membership = get_membership(workspace_id, user_id)
    return bool(membership and membership.role in roles)


def project_access(project):
    if not project:
        return False

    if project.workspace_id:
        workspace = db.session.get(Workspace, project.workspace_id)
        if not workspace or workspace.is_archived:
            return False

        if not get_membership(project.workspace_id, current_user.id):
            return False

    if project.owner_id == current_user.id:
        return True

    membership = ProjectMembership.query.filter_by(
        project_id=project.id,
        user_id=current_user.id,
    ).first()

    if membership:
        return True

    return bool(project.workspace_id)


def can_manage_project(project):
    if project.owner_id == current_user.id:
        return True

    membership = ProjectMembership.query.filter_by(
        project_id=project.id,
        user_id=current_user.id,
    ).first()

    if membership and membership.role in ("owner", "manager"):
        return True

    if project.workspace_id:
        return has_role(
            project.workspace_id,
            current_user.id,
            ["owner", "admin", "manager"],
        )

    return False


def workspace_json(workspace, membership=None):
    return {
        "id": workspace.id,
        "name": workspace.name,
        "slug": workspace.slug,
        "description": workspace.description,
        "owner_id": workspace.owner_id,
        "is_archived": workspace.is_archived,
        "role": membership.role if membership else None,
    }


def project_json(project):
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "owner_id": project.owner_id,
        "workspace_id": project.workspace_id,
        "status": project.status,
        "priority": project.priority,
        "completed_at": (
            project.completed_at.isoformat()
            if project.completed_at else None
        ),
        "start_date": (
            project.start_date.isoformat()
            if project.start_date else None
        ),
        "due_date": (
            project.due_date.isoformat()
            if project.due_date else None
        ),
    }


@business_api.route("/workspaces", methods=["GET", "POST"])
@login_required
def workspaces():
    if request.method == "GET":
        memberships = WorkspaceMembership.query.filter_by(
            user_id=current_user.id,
            status="active",
        ).all()

        result = []
        for membership in memberships:
            workspace = db.session.get(
                Workspace, membership.workspace_id
            )
            if workspace and not workspace.is_archived:
                result.append(workspace_json(workspace, membership))

        return jsonify({"workspaces": result})

    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    description = str(data.get("description", "")).strip()

    if not 3 <= len(name) <= 150:
        return error("Workspace name must be 3-150 characters")

    if len(description) > 3000:
        return error("Description is too long")

    base_slug = re.sub(
        r"[^a-z0-9]+", "-", name.lower()
    ).strip("-")[:140]

    if not base_slug:
        return error("Workspace name must contain letters or numbers")

    slug = base_slug
    suffix = 2

    while Workspace.query.filter_by(slug=slug).first():
        slug = f"{base_slug[:130]}-{suffix}"
        suffix += 1

    workspace = Workspace(
        name=name,
        slug=slug,
        description=description,
        owner_id=current_user.id,
        is_archived=False,
    )

    db.session.add(workspace)
    db.session.flush()

    membership = WorkspaceMembership(
        workspace_id=workspace.id,
        user_id=current_user.id,
        role="owner",
        status="active",
    )

    db.session.add(membership)
    db.session.commit()

    return jsonify({
        "message": "Workspace created",
        "workspace": workspace_json(workspace, membership),
    }), 201


@business_api.get("/workspaces/<int:workspace_id>")
@login_required
def get_workspace(workspace_id):
    workspace = db.session.get(Workspace, workspace_id)
    membership = get_membership(workspace_id, current_user.id)

    if not workspace or workspace.is_archived or not membership:
        return error("Workspace not found", 404)

    return jsonify({"workspace": workspace_json(workspace, membership)})


@business_api.patch("/workspaces/<int:workspace_id>")
@login_required
def update_workspace(workspace_id):
    workspace = db.session.get(Workspace, workspace_id)

    if not workspace or workspace.is_archived:
        return error("Workspace not found", 404)

    if not has_role(workspace_id, current_user.id, ["owner", "admin"]):
        return error("Insufficient permissions", 403)

    data = request.get_json(silent=True) or {}

    if "name" in data:
        name = str(data["name"]).strip()
        if not 3 <= len(name) <= 150:
            return error("Name must be 3-150 characters")
        workspace.name = name

    if "description" in data:
        description = str(data["description"]).strip()
        if len(description) > 3000:
            return error("Description is too long")
        workspace.description = description

    if "is_archived" in data:
        if workspace.owner_id != current_user.id:
            return error("Only the owner can archive", 403)
        if not isinstance(data["is_archived"], bool):
            return error("is_archived must be true or false")
        workspace.is_archived = data["is_archived"]

    db.session.commit()

    return jsonify({
        "message": "Workspace updated",
        "workspace": workspace_json(
            workspace, get_membership(workspace_id, current_user.id)
        ),
    })


# WORKSPACE MEMBERS

@business_api.get("/workspaces/<int:workspace_id>/members")
@login_required
def workspace_members(workspace_id):
    if not get_membership(workspace_id, current_user.id):
        return error("Workspace not found", 404)

    memberships = WorkspaceMembership.query.filter_by(
        workspace_id=workspace_id,
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


@business_api.post("/workspaces/<int:workspace_id>/members")
@login_required
def add_workspace_member(workspace_id):
    workspace = db.session.get(Workspace, workspace_id)

    if not workspace or workspace.is_archived:
        return error("Workspace not found", 404)

    if not has_role(workspace_id, current_user.id, ["owner", "admin"]):
        return error("Insufficient permissions", 403)

    data = request.get_json(silent=True) or {}

    try:
        user_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return error("Valid user_id is required")

    if not db.session.get(User, user_id):
        return error("User not found", 404)

    role = str(data.get("role", "member")).lower()
    if role not in ("admin", "member"):
        return error("Role must be admin or member")

    if role == "admin" and workspace.owner_id != current_user.id:
        return error("Only the owner can appoint admins", 403)

    existing = WorkspaceMembership.query.filter_by(
        workspace_id=workspace_id,
        user_id=user_id,
    ).first()

    if existing:
        if existing.status == "active":
            return error("User is already a member", 409)
        existing.status = "active"
        existing.role = role
    else:
        db.session.add(WorkspaceMembership(
            workspace_id=workspace_id,
            user_id=user_id,
            role=role,
            status="active",
        ))

    db.session.commit()
    return jsonify({"message": "Workspace member added"}), 201


@business_api.patch(
    "/workspaces/<int:workspace_id>/members/<int:user_id>"
)
@login_required
def update_workspace_member(workspace_id, user_id):
    workspace = db.session.get(Workspace, workspace_id)

    if not workspace:
        return error("Workspace not found", 404)

    if workspace.owner_id != current_user.id:
        return error("Only the owner can manage member roles", 403)

    membership = WorkspaceMembership.query.filter_by(
        workspace_id=workspace_id,
        user_id=user_id,
    ).first()

    if not membership:
        return error("Membership not found", 404)

    if user_id == workspace.owner_id:
        return error("Owner membership cannot be changed", 403)

    data = request.get_json(silent=True) or {}

    if "role" in data:
        role = str(data["role"]).lower()
        if role not in ("admin", "member"):
            return error("Role must be admin or member")
        membership.role = role

    if "status" in data:
        status = str(data["status"]).lower()
        if status not in ("active", "suspended"):
            return error("Status must be active or suspended")
        membership.status = status

    db.session.commit()

    return jsonify({
        "message": "Membership updated",
        "user_id": user_id,
        "role": membership.role,
        "status": membership.status,
    })


# TEAMS

@business_api.route(
    "/workspaces/<int:workspace_id>/teams",
    methods=["GET", "POST"],
)
@login_required
def workspace_teams(workspace_id):
    workspace = db.session.get(Workspace, workspace_id)

    if not workspace or not get_membership(
        workspace_id, current_user.id
    ):
        return error("Workspace not found", 404)

    if request.method == "GET":
        teams = Team.query.filter_by(
            workspace_id=workspace_id
        ).order_by(Team.id.desc()).all()

        return jsonify({
            "teams": [{
                "id": team.id,
                "name": team.name,
                "description": team.description,
                "workspace_id": team.workspace_id,
            } for team in teams]
        })

    if not has_role(workspace_id, current_user.id, ["owner", "admin"]):
        return error("Insufficient permissions", 403)

    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    description = str(data.get("description", "")).strip()

    if not 2 <= len(name) <= 120:
        return error("Team name must be 2-120 characters")

    if len(description) > 2000:
        return error("Description is too long")

    team = Team(
        workspace_id=workspace_id,
        name=name,
        description=description,
    )

    db.session.add(team)
    db.session.flush()

    db.session.add(TeamMembership(
        team_id=team.id,
        user_id=current_user.id,
        role="lead",
    ))

    db.session.commit()

    return jsonify({
        "message": "Team created",
        "team_id": team.id,
        "name": team.name,
    }), 201


@business_api.post("/teams/<int:team_id>/members")
@login_required
def add_team_member(team_id):
    team = db.session.get(Team, team_id)

    if not team:
        return error("Team not found", 404)

    if not has_role(
        team.workspace_id, current_user.id, ["owner", "admin"]
    ):
        return error("Insufficient permissions", 403)

    data = request.get_json(silent=True) or {}

    try:
        user_id = int(data.get("user_id"))
    except (TypeError, ValueError):
        return error("Valid user_id is required")

    if not db.session.get(User, user_id):
        return error("User not found", 404)

    if not get_membership(team.workspace_id, user_id):
        return error("User must be an active workspace member", 400)

    existing = TeamMembership.query.filter_by(
        team_id=team_id,
        user_id=user_id,
    ).first()

    if existing:
        return error("User is already in this team", 409)

    role = str(data.get("role", "member")).lower()
    if role not in ("lead", "member"):
        return error("Role must be lead or member")

    db.session.add(TeamMembership(
        team_id=team_id,
        user_id=user_id,
        role=role,
    ))

    db.session.commit()
    return jsonify({"message": "Team member added"}), 201


# PROJECTS

@business_api.route("/projects", methods=["GET", "POST"])
@login_required
def projects():
    if request.method == "GET":
        memberships = ProjectMembership.query.filter_by(
            user_id=current_user.id
        ).all()

        project_ids = {item.project_id for item in memberships}

        query = Project.query.filter(
            Project.owner_id == current_user.id
        )

        if project_ids:
            query = Project.query.filter(
                (Project.owner_id == current_user.id)
                | Project.id.in_(project_ids)
            )

        result = []
        for project in query.order_by(Project.id.desc()).all():
            if project_access(project):
                result.append(project_json(project))

        return jsonify({"projects": result})

    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    description = str(data.get("description", "")).strip()

    if not 2 <= len(name) <= 150:
        return error("Project name must be 2-150 characters")

    if len(description) > 5000:
        return error("Description is too long")

    workspace_id = data.get("workspace_id")

    if workspace_id is not None:
        try:
            workspace_id = int(workspace_id)
        except (TypeError, ValueError):
            return error("Invalid workspace_id")

        if not get_membership(workspace_id, current_user.id):
            return error("Workspace not found", 404)

    status = str(data.get("status", "active")).lower()
    priority = str(data.get("priority", "medium")).lower()

    if status not in ("active", "on_hold", "completed", "archived"):
        return error("Invalid project status")

    if priority not in ("low", "medium", "high", "urgent"):
        return error("Invalid project priority")

    start_date = None
    due_date = None

    if data.get("start_date"):
        try:
            start_date = date.fromisoformat(data["start_date"])
        except (ValueError, TypeError):
            return error("start_date must use YYYY-MM-DD")

    if data.get("due_date"):
        try:
            due_date = date.fromisoformat(data["due_date"])
        except (ValueError, TypeError):
            return error("due_date must use YYYY-MM-DD")

    if start_date and due_date and due_date < start_date:
        return error("Due date cannot precede start date")

    project = Project(
        name=name,
        description=description,
        owner_id=current_user.id,
        workspace_id=workspace_id,
        status=status,
        priority=priority,
        start_date=start_date,
        due_date=due_date,
    )

    db.session.add(project)
    db.session.flush()

    db.session.add(ProjectMembership(
        project_id=project.id,
        user_id=current_user.id,
        role="owner",
    ))

    db.session.commit()

    return jsonify({
        "message": "Project created",
        "project": project_json(project),
    }), 201


@business_api.get("/projects/<int:project_id>")
@login_required
def get_project(project_id):
    project = db.session.get(Project, project_id)

    if not project or not project_access(project):
        return error("Project not found", 404)

    return jsonify({"project": project_json(project)})


@business_api.patch("/projects/<int:project_id>")
@login_required
def update_project(project_id):
    project = db.session.get(Project, project_id)

    if not project or not project_access(project):
        return error("Project not found", 404)

    membership = ProjectMembership.query.filter_by(
        project_id=project.id,
        user_id=current_user.id,
    ).first()

    if project.owner_id != current_user.id and not (
        membership and membership.role in ("owner", "manager")
    ):
        return error("Insufficient permissions", 403)

    data = request.get_json(silent=True) or {}

    if "name" in data:
        name = str(data["name"]).strip()
        if not 2 <= len(name) <= 150:
            return error("Project name must be 2-150 characters")
        project.name = name

    if "description" in data:
        description = str(data["description"]).strip()
        if len(description) > 5000:
            return error("Description is too long")
        project.description = description

    if "status" in data:
        status = str(data["status"]).lower()
        if status not in ("active", "on_hold", "completed", "archived"):
            return error("Invalid project status")
        project.status = status
        if status == "completed":
            if project.completed_at is None:
                project.completed_at = datetime.now(timezone.utc)
        else:
            project.completed_at = None

    if "priority" in data:
        priority = str(data["priority"]).lower()
        if priority not in ("low", "medium", "high", "urgent"):
            return error("Invalid project priority")
        project.priority = priority

    if "start_date" in data:
        value = data["start_date"]
        try:
            project.start_date = date.fromisoformat(value) if value else None
        except (ValueError, TypeError):
            return error("Invalid start_date")

    if "due_date" in data:
        value = data["due_date"]
        try:
            project.due_date = date.fromisoformat(value) if value else None
        except (ValueError, TypeError):
            return error("Invalid due_date")

    if (
        project.start_date
        and project.due_date
        and project.due_date < project.start_date
    ):
        return error("Due date cannot precede start date")

    db.session.commit()

    return jsonify({
        "message": "Project updated",
        "project": project_json(project),
    })


@business_api.post("/projects/<int:project_id>/members")
@login_required
def add_project_member(project_id):
    project = db.session.get(Project, project_id)

    if not project or not project_access(project):
        return error("Project not found", 404)

    if project.owner_id != current_user.id:
        return error("Only the project owner can add members", 403)

    data = request.get_json(silent=True) or {}

    try:
        user_id = int(data.get("user_id"))
    except (ValueError, TypeError):
        return error("Valid user_id is required")

    if not db.session.get(User, user_id):
        return error("User not found", 404)

    if project.workspace_id and not get_membership(
        project.workspace_id, user_id
    ):
        return error("User must be an active workspace member", 400)

    existing = ProjectMembership.query.filter_by(
        project_id=project_id,
        user_id=user_id,
    ).first()

    if existing:
        return error("User is already a project member", 409)

    role = str(data.get("role", "member")).lower()

    if role not in ("manager", "member"):
        return error("Role must be manager or member")

    db.session.add(ProjectMembership(
        project_id=project_id,
        user_id=user_id,
        role=role,
    ))

    db.session.commit()
    return jsonify({"message": "Project member added"}), 201


# PROJECT TASKS

@business_api.route(
    "/projects/<int:project_id>/tasks",
    methods=["GET", "POST"],
)
@login_required
def project_tasks(project_id):
    project = db.session.get(Project, project_id)

    if not project or not project_access(project):
        return error("Project not found", 404)

    if request.method == "GET":
        tasks = Task.query.filter_by(
            project_id=project_id
        ).order_by(Task.id.desc()).all()

        return jsonify({
            "tasks": [
                {
                    "id": task.id,
                    "title": task.title,
                    "description": task.description,
                    "creator_id": task.creator_id,
                    "assignee_id": task.assignee_id,
                    "project_id": task.project_id,
                    "status": task.status,
                    "priority": task.priority,
                    "due_at": (
                        task.due_at.isoformat()
                        if task.due_at else None
                    ),
                }
                for task in tasks
            ]
        })

    if not can_manage_project(project):
        return error("Insufficient permissions to create project tasks", 403)

    data = request.get_json(silent=True) or {}
    title = str(data.get("title", "")).strip()
    description = str(data.get("description", "")).strip()

    if not 2 <= len(title) <= 200:
        return error("Task title must be 2-200 characters")

    if len(description) > 5000:
        return error("Task description is too long")

    assignee_id = data.get("assignee_id")

    if assignee_id is not None:
        try:
            assignee_id = int(assignee_id)
        except (ValueError, TypeError):
            return error("Invalid assignee_id")

        if not db.session.get(User, assignee_id):
            return error("Assignee not found", 404)

        if project.workspace_id and not get_membership(
            project.workspace_id, assignee_id
        ):
            return error("Assignee must be a workspace member", 400)

    status = str(data.get("status", "todo")).lower()
    priority = str(data.get("priority", "medium")).lower()

    if status not in ("todo", "in_progress", "blocked", "completed", "cancelled"):
        return error("Invalid task status")

    if priority not in ("low", "medium", "high", "urgent"):
        return error("Invalid task priority")

    task = Task(
        title=title,
        description=description,
        creator_id=current_user.id,
        assignee_id=assignee_id,
        project_id=project_id,
        status=status,
        priority=priority,
    )

    db.session.add(task)
    db.session.commit()

    return jsonify({
        "message": "Project task created",
        "task_id": task.id,
    }), 201
