from datetime import date, datetime

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import or_

from models import db
from extended_models import (
    Task,
    Goal,
    Note,
    CalendarEvent,
    Reminder,
)

productivity = Blueprint(
    "productivity",
    __name__,
    url_prefix="/api",
)


def payload():
    return request.get_json(silent=True) or {}


def parse_datetime(value):
    if not value:
        return None

    try:
        result = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
        return result
    except (TypeError, ValueError):
        raise ValueError("Invalid datetime. Use ISO 8601 format.")


def parse_date(value):
    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("Invalid date. Use YYYY-MM-DD format.")


def error(message, status=400):
    return jsonify({"error": message}), status


def task_json(task):
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "creator_id": task.creator_id,
        "assignee_id": task.assignee_id,
        "project_id": task.project_id,
        "parent_task_id": task.parent_task_id,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "completed_at": (
            task.completed_at.isoformat()
            if task.completed_at else None
        ),
        "created_at": task.created_at.isoformat(),
    }


def goal_json(goal):
    return {
        "id": goal.id,
        "title": goal.title,
        "description": goal.description,
        "status": goal.status,
        "target_date": (
            goal.target_date.isoformat()
            if goal.target_date else None
        ),
        "progress_percent": goal.progress_percent,
    }


def note_json(note):
    return {
        "id": note.id,
        "title": note.title,
        "content": note.content,
        "category": note.category,
        "tags": note.tags,
        "is_pinned": note.is_pinned,
        "is_archived": note.is_archived,
        "created_at": note.created_at.isoformat(),
        "updated_at": note.updated_at.isoformat(),
    }


def event_json(event):
    return {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "starts_at": event.starts_at.isoformat(),
        "ends_at": event.ends_at.isoformat() if event.ends_at else None,
        "timezone_name": event.timezone_name,
        "location": event.location,
        "is_all_day": event.is_all_day,
    }


def reminder_json(reminder):
    return {
        "id": reminder.id,
        "title": reminder.title,
        "description": reminder.description,
        "remind_at": reminder.remind_at.isoformat(),
        "related_type": reminder.related_type,
        "related_id": reminder.related_id,
        "status": reminder.status,
        "delivered_at": (
            reminder.delivered_at.isoformat()
            if reminder.delivered_at else None
        ),
    }


# =====================================================
# TASKS
# =====================================================

@productivity.route("/tasks", methods=["GET", "POST"])
@login_required
def tasks_collection():
    if request.method == "GET":
        query = Task.query.filter(
            or_(
                Task.creator_id == current_user.id,
                Task.assignee_id == current_user.id,
            )
        )

        status = request.args.get("status")
        if status:
            query = query.filter(Task.status == status)

        items = query.order_by(Task.created_at.desc()).limit(200).all()

        return jsonify({
            "items": [task_json(item) for item in items]
        })

    data = payload()
    title = str(data.get("title", "")).strip()
    description = str(data.get("description", "")).strip()

    if not title or len(title) > 200:
        return error("Title is required and must be at most 200 characters.")

    if len(description) > 10000:
        return error("Description is too long.")

    status = data.get("status", "todo")
    priority = data.get("priority", "medium")

    if status not in (
        "todo", "in_progress", "blocked", "completed", "cancelled"
    ):
        return error("Invalid task status.")

    if priority not in ("low", "medium", "high", "urgent"):
        return error("Invalid task priority.")

    try:
        due_at = parse_datetime(data.get("due_at"))
    except ValueError as exc:
        return error(str(exc))

    task = Task(
        title=title,
        description=description or None,
        creator_id=current_user.id,
        assignee_id=current_user.id,
        status=status,
        priority=priority,
        due_at=due_at,
    )

    db.session.add(task)
    db.session.commit()

    return jsonify({"item": task_json(task)}), 201


@productivity.route("/tasks/<int:task_id>", methods=["GET", "PATCH", "DELETE"])
@login_required
def task_detail(task_id):
    task = db.session.get(Task, task_id)

    if task is None:
        return error("Task not found.", 404)

    if current_user.id not in (task.creator_id, task.assignee_id):
        return error("You do not have access to this task.", 403)

    if request.method == "GET":
        return jsonify({"item": task_json(task)})

    if request.method == "DELETE":
        if task.creator_id != current_user.id:
            return error("Only the task creator can delete this task.", 403)

        db.session.delete(task)
        db.session.commit()
        return jsonify({"message": "Task deleted."})

    data = payload()

    if "title" in data:
        title = str(data["title"]).strip()
        if not title or len(title) > 200:
            return error("Title must be 1-200 characters.")
        task.title = title

    if "description" in data:
        description = str(data["description"]).strip()
        if len(description) > 10000:
            return error("Description is too long.")
        task.description = description or None

    if "status" in data:
        if data["status"] not in (
            "todo", "in_progress", "blocked", "completed", "cancelled"
        ):
            return error("Invalid task status.")
        task.status = data["status"]

        if task.status == "completed":
            task.completed_at = datetime.now().astimezone()
        else:
            task.completed_at = None

    if "priority" in data:
        if data["priority"] not in ("low", "medium", "high", "urgent"):
            return error("Invalid task priority.")
        task.priority = data["priority"]

    if "due_at" in data:
        try:
            task.due_at = parse_datetime(data["due_at"])
        except ValueError as exc:
            return error(str(exc))

    db.session.commit()
    return jsonify({"item": task_json(task)})


# =====================================================
# GOALS
# =====================================================

@productivity.route("/goals", methods=["GET", "POST"])
@login_required
def goals_collection():
    if request.method == "GET":
        items = Goal.query.filter_by(
            user_id=current_user.id
        ).order_by(Goal.created_at.desc()).all()

        return jsonify({"items": [goal_json(item) for item in items]})

    data = payload()
    title = str(data.get("title", "")).strip()
    description = str(data.get("description", "")).strip()

    if not title or len(title) > 200:
        return error("Goal title is required and limited to 200 characters.")

    try:
        target_date = parse_date(data.get("target_date"))
    except ValueError as exc:
        return error(str(exc))

    goal = Goal(
        user_id=current_user.id,
        title=title,
        description=description or None,
        target_date=target_date,
    )

    db.session.add(goal)
    db.session.commit()

    return jsonify({"item": goal_json(goal)}), 201


@productivity.route("/goals/<int:goal_id>", methods=["GET", "PATCH", "DELETE"])
@login_required
def goal_detail(goal_id):
    goal = db.session.get(Goal, goal_id)

    if goal is None:
        return error("Goal not found.", 404)

    if goal.user_id != current_user.id:
        return error("You do not have access to this goal.", 403)

    if request.method == "GET":
        return jsonify({"item": goal_json(goal)})

    if request.method == "DELETE":
        db.session.delete(goal)
        db.session.commit()
        return jsonify({"message": "Goal deleted."})

    data = payload()

    if "title" in data:
        title = str(data["title"]).strip()
        if not title or len(title) > 200:
            return error("Goal title must be 1-200 characters.")
        goal.title = title

    if "description" in data:
        description = str(data["description"]).strip()
        goal.description = description or None

    if "status" in data:
        if data["status"] not in (
            "active", "completed", "paused", "cancelled"
        ):
            return error("Invalid goal status.")
        goal.status = data["status"]

    if "progress_percent" in data:
        progress = data["progress_percent"]

        if type(progress) is not int or not 0 <= progress <= 100:
            return error("Progress must be an integer from 0 to 100.")

        goal.progress_percent = progress

    if "target_date" in data:
        try:
            goal.target_date = parse_date(data["target_date"])
        except ValueError as exc:
            return error(str(exc))

    db.session.commit()
    return jsonify({"item": goal_json(goal)})


# =====================================================
# NOTES
# =====================================================

@productivity.route("/notes", methods=["GET", "POST"])
@login_required
def notes_collection():
    if request.method == "GET":
        query = Note.query.filter_by(user_id=current_user.id)

        if request.args.get("archived") == "true":
            query = query.filter_by(is_archived=True)
        else:
            query = query.filter_by(is_archived=False)

        items = query.order_by(
            Note.is_pinned.desc(),
            Note.updated_at.desc(),
        ).limit(200).all()

        return jsonify({"items": [note_json(item) for item in items]})

    data = payload()
    title = str(data.get("title", "")).strip()
    content = str(data.get("content", ""))

    if not title or len(title) > 200:
        return error("Note title is required and limited to 200 characters.")

    if len(content) > 100000:
        return error("Note content is too long.")

    tags = data.get("tags", [])

    if not isinstance(tags, list) or len(tags) > 30:
        return error("Tags must be a list containing at most 30 items.")

    if any(not isinstance(tag, str) or len(tag) > 50 for tag in tags):
        return error("Each tag must be a string of at most 50 characters.")

    note = Note(
        user_id=current_user.id,
        title=title,
        content=content,
        category=str(data.get("category", ""))[:80] or None,
        tags=tags,
    )

    db.session.add(note)
    db.session.commit()

    return jsonify({"item": note_json(note)}), 201


@productivity.route("/notes/<int:note_id>", methods=["GET", "PATCH", "DELETE"])
@login_required
def note_detail(note_id):
    note = db.session.get(Note, note_id)

    if note is None:
        return error("Note not found.", 404)

    if note.user_id != current_user.id:
        return error("You do not have access to this note.", 403)

    if request.method == "GET":
        return jsonify({"item": note_json(note)})

    if request.method == "DELETE":
        db.session.delete(note)
        db.session.commit()
        return jsonify({"message": "Note deleted."})

    data = payload()

    if "title" in data:
        title = str(data["title"]).strip()
        if not title or len(title) > 200:
            return error("Note title must be 1-200 characters.")
        note.title = title

    if "content" in data:
        content = str(data["content"])
        if len(content) > 100000:
            return error("Note content is too long.")
        note.content = content

    if "category" in data:
        note.category = str(data["category"])[:80] or None

    if "tags" in data:
        tags = data["tags"]
        if (
            not isinstance(tags, list)
            or len(tags) > 30
            or any(not isinstance(tag, str) or len(tag) > 50 for tag in tags)
        ):
            return error("Invalid tags.")
        note.tags = tags

    if "is_pinned" in data:
        if type(data["is_pinned"]) is not bool:
            return error("is_pinned must be true or false.")
        note.is_pinned = data["is_pinned"]

    if "is_archived" in data:
        if type(data["is_archived"]) is not bool:
            return error("is_archived must be true or false.")
        note.is_archived = data["is_archived"]

    db.session.commit()
    return jsonify({"item": note_json(note)})


# =====================================================
# CALENDAR EVENTS
# =====================================================

@productivity.route("/calendar/events", methods=["GET", "POST"])
@login_required
def calendar_collection():
    if request.method == "GET":
        items = CalendarEvent.query.filter_by(
            user_id=current_user.id
        ).order_by(CalendarEvent.starts_at.asc()).limit(500).all()

        return jsonify({"items": [event_json(item) for item in items]})

    data = payload()
    title = str(data.get("title", "")).strip()

    if not title or len(title) > 200:
        return error("Event title is required and limited to 200 characters.")

    try:
        starts_at = parse_datetime(data.get("starts_at"))
        ends_at = parse_datetime(data.get("ends_at"))
    except ValueError as exc:
        return error(str(exc))

    if starts_at is None:
        return error("starts_at is required.")

    if ends_at and ends_at < starts_at:
        return error("Event end cannot be earlier than its start.")

    event = CalendarEvent(
        user_id=current_user.id,
        title=title,
        description=str(data.get("description", ""))[:10000] or None,
        starts_at=starts_at,
        ends_at=ends_at,
        timezone_name=str(data.get("timezone_name", "UTC"))[:64],
        location=str(data.get("location", ""))[:250] or None,
        is_all_day=data.get("is_all_day", False),
    )

    db.session.add(event)
    db.session.commit()

    return jsonify({"item": event_json(event)}), 201


@productivity.route(
    "/calendar/events/<int:event_id>",
    methods=["GET", "PATCH", "DELETE"],
)
@login_required
def calendar_detail(event_id):
    event = db.session.get(CalendarEvent, event_id)

    if event is None:
        return error("Event not found.", 404)

    if event.user_id != current_user.id:
        return error("You do not have access to this event.", 403)

    if request.method == "GET":
        return jsonify({"item": event_json(event)})

    if request.method == "DELETE":
        db.session.delete(event)
        db.session.commit()
        return jsonify({"message": "Event deleted."})

    data = payload()

    if "title" in data:
        title = str(data["title"]).strip()
        if not title or len(title) > 200:
            return error("Event title must be 1-200 characters.")
        event.title = title

    if "description" in data:
        event.description = str(data["description"])[:10000] or None

    try:
        if "starts_at" in data:
            event.starts_at = parse_datetime(data["starts_at"])
            if event.starts_at is None:
                return error("starts_at cannot be empty.")

        if "ends_at" in data:
            event.ends_at = parse_datetime(data["ends_at"])
    except ValueError as exc:
        return error(str(exc))

    if event.ends_at and event.ends_at < event.starts_at:
        return error("Event end cannot be earlier than its start.")

    if "location" in data:
        event.location = str(data["location"])[:250] or None

    if "timezone_name" in data:
        event.timezone_name = str(data["timezone_name"])[:64]

    if "is_all_day" in data:
        if type(data["is_all_day"]) is not bool:
            return error("is_all_day must be true or false.")
        event.is_all_day = data["is_all_day"]

    db.session.commit()
    return jsonify({"item": event_json(event)})


# =====================================================
# REMINDERS
# =====================================================

@productivity.route("/reminders", methods=["GET", "POST"])
@login_required
def reminders_collection():
    if request.method == "GET":
        items = Reminder.query.filter_by(
            user_id=current_user.id
        ).order_by(Reminder.remind_at.asc()).limit(500).all()

        return jsonify({
            "items": [reminder_json(item) for item in items]
        })

    data = payload()
    title = str(data.get("title", "")).strip()

    if not title or len(title) > 200:
        return error("Reminder title is required and limited to 200 characters.")

    try:
        remind_at = parse_datetime(data.get("remind_at"))
    except ValueError as exc:
        return error(str(exc))

    if remind_at is None:
        return error("remind_at is required.")

    reminder = Reminder(
        user_id=current_user.id,
        title=title,
        description=str(data.get("description", ""))[:10000] or None,
        remind_at=remind_at,
        related_type=str(data.get("related_type", ""))[:40] or None,
        related_id=data.get("related_id"),
    )

    db.session.add(reminder)
    db.session.commit()

    return jsonify({"item": reminder_json(reminder)}), 201


@productivity.route(
    "/reminders/<int:reminder_id>",
    methods=["GET", "PATCH", "DELETE"],
)
@login_required
def reminder_detail(reminder_id):
    reminder = db.session.get(Reminder, reminder_id)

    if reminder is None:
        return error("Reminder not found.", 404)

    if reminder.user_id != current_user.id:
        return error("You do not have access to this reminder.", 403)

    if request.method == "GET":
        return jsonify({"item": reminder_json(reminder)})

    if request.method == "DELETE":
        db.session.delete(reminder)
        db.session.commit()
        return jsonify({"message": "Reminder deleted."})

    data = payload()

    if "title" in data:
        title = str(data["title"]).strip()
        if not title or len(title) > 200:
            return error("Reminder title must be 1-200 characters.")
        reminder.title = title

    if "description" in data:
        reminder.description = str(data["description"])[:10000] or None

    if "remind_at" in data:
        try:
            remind_at = parse_datetime(data["remind_at"])
        except ValueError as exc:
            return error(str(exc))

        if remind_at is None:
            return error("remind_at cannot be empty.")

        reminder.remind_at = remind_at

    if "status" in data:
        if data["status"] not in ("pending", "delivered", "cancelled"):
            return error("Invalid reminder status.")
        reminder.status = data["status"]

    db.session.commit()
    return jsonify({"item": reminder_json(reminder)})
