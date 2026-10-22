from sqlalchemy import CheckConstraint, UniqueConstraint
from models import db


class TimestampMixin:
    created_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now(),
        nullable=False
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now(),
        onupdate=db.func.now(),
        nullable=False
    )


# ==================== NOTIFICATIONS ====================

class Notification(TimestampMixin, db.Model):
    __tablename__ = "notification"

    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    actor_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True
    )
    notification_type = db.Column(db.String(40), nullable=False)
    object_type = db.Column(db.String(40))
    object_id = db.Column(db.Integer)
    message = db.Column(db.String(500), nullable=False)
    is_read = db.Column(db.Boolean, default=False, nullable=False)

    recipient = db.relationship("User", foreign_keys=[recipient_id])
    actor = db.relationship("User", foreign_keys=[actor_id])


# ==================== MESSAGING ====================

class Conversation(TimestampMixin, db.Model):
    __tablename__ = "conversation"

    id = db.Column(db.Integer, primary_key=True)
    conversation_type = db.Column(
        db.String(20), default="direct", nullable=False
    )
    title = db.Column(db.String(120))
    created_by_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="SET NULL")
    )
    is_archived = db.Column(db.Boolean, default=False, nullable=False)

    created_by = db.relationship("User", foreign_keys=[created_by_id])
    participants = db.relationship(
        "ConversationParticipant",
        back_populates="conversation",
        cascade="all, delete-orphan"
    )
    messages = db.relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at.asc()"
    )


class ConversationParticipant(TimestampMixin, db.Model):
    __tablename__ = "conversation_participant"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey("conversation.id", ondelete="CASCADE"),
        nullable=False
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False
    )
    last_read_at = db.Column(db.DateTime(timezone=True))
    is_muted = db.Column(db.Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "user_id",
            name="unique_conversation_participant"
        ),
    )

    conversation = db.relationship(
        "Conversation", back_populates="participants"
    )
    user = db.relationship("User")


class Message(TimestampMixin, db.Model):
    __tablename__ = "message"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey("conversation.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    sender_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="SET NULL")
    )
    body = db.Column(db.String(10000), nullable=False, default="")
    edited_at = db.Column(db.DateTime(timezone=True))
    deleted_at = db.Column(db.DateTime(timezone=True))

    conversation = db.relationship(
        "Conversation", back_populates="messages"
    )
    sender = db.relationship("User", foreign_keys=[sender_id])


# ==================== COMMUNITIES ====================

class Community(TimestampMixin, db.Model):
    __tablename__ = "community"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(120), unique=True, nullable=False, index=True)
    description = db.Column(db.String(2000))
    owner_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"),
        nullable=False
    )
    visibility = db.Column(
        db.String(20), default="public", nullable=False
    )
    is_archived = db.Column(db.Boolean, default=False, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "visibility IN ('public', 'private')",
            name="valid_community_visibility"
        ),
    )

    owner = db.relationship("User", foreign_keys=[owner_id])
    memberships = db.relationship(
        "CommunityMembership",
        back_populates="community",
        cascade="all, delete-orphan"
    )


class CommunityMembership(TimestampMixin, db.Model):
    __tablename__ = "community_membership"

    id = db.Column(db.Integer, primary_key=True)
    community_id = db.Column(
        db.Integer, db.ForeignKey("community.id", ondelete="CASCADE"),
        nullable=False
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False
    )
    role = db.Column(db.String(20), default="member", nullable=False)
    status = db.Column(db.String(20), default="active", nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "community_id", "user_id",
            name="unique_community_membership"
        ),
        CheckConstraint(
            "role IN ('owner', 'moderator', 'member')",
            name="valid_community_role"
        ),
        CheckConstraint(
            "status IN ('pending', 'active', 'banned')",
            name="valid_community_membership_status"
        ),
    )

    community = db.relationship(
        "Community", back_populates="memberships"
    )
    user = db.relationship("User")


# ==================== POST BOOKMARKS ====================

class PostBookmark(TimestampMixin, db.Model):
    __tablename__ = "post_bookmark"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(
        db.Integer, db.ForeignKey("post.id", ondelete="CASCADE"),
        nullable=False
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "post_id", "user_id", name="unique_post_bookmark"
        ),
    )

    post = db.relationship("Post")
    user = db.relationship("User")


# ==================== WORKSPACES ====================

class Workspace(TimestampMixin, db.Model):
    __tablename__ = "workspace"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    slug = db.Column(db.String(160), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    owner_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )
    is_archived = db.Column(db.Boolean, default=False, nullable=False)

    owner = db.relationship("User", foreign_keys=[owner_id])

    memberships = db.relationship(
        "WorkspaceMembership",
        back_populates="workspace",
        cascade="all, delete-orphan"
    )

    teams = db.relationship(
        "Team",
        back_populates="workspace",
        cascade="all, delete-orphan"
    )

    projects = db.relationship(
        "Project",
        back_populates="workspace"
    )


class WorkspaceMembership(TimestampMixin, db.Model):
    __tablename__ = "workspace_membership"

    id = db.Column(db.Integer, primary_key=True)

    workspace_id = db.Column(
        db.Integer, db.ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False
    )

    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False
    )

    role = db.Column(db.String(20), default="member", nullable=False)
    status = db.Column(db.String(20), default="active", nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "user_id",
            name="unique_workspace_membership"
        ),
        CheckConstraint(
            "role IN ('owner', 'admin', 'manager', 'member', 'viewer')",
            name="valid_workspace_role"
        ),
        CheckConstraint(
            "status IN ('invited', 'active', 'suspended')",
            name="valid_workspace_membership_status"
        ),
    )

    workspace = db.relationship(
        "Workspace", back_populates="memberships"
    )
    user = db.relationship("User")


# ==================== TEAMS ====================

class Team(TimestampMixin, db.Model):
    __tablename__ = "team"

    id = db.Column(db.Integer, primary_key=True)

    workspace_id = db.Column(
        db.Integer, db.ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text)

    workspace = db.relationship(
        "Workspace", back_populates="teams"
    )

    memberships = db.relationship(
        "TeamMembership",
        back_populates="team",
        cascade="all, delete-orphan"
    )


class TeamMembership(TimestampMixin, db.Model):
    __tablename__ = "team_membership"

    id = db.Column(db.Integer, primary_key=True)

    team_id = db.Column(
        db.Integer, db.ForeignKey("team.id", ondelete="CASCADE"),
        nullable=False
    )

    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False
    )

    role = db.Column(db.String(20), default="member", nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "team_id", "user_id",
            name="unique_team_membership"
        ),
        CheckConstraint(
            "role IN ('lead', 'member')",
            name="valid_team_role"
        ),
    )

    team = db.relationship("Team", back_populates="memberships")
    user = db.relationship("User")


# ==================== PROJECTS ====================

class Project(TimestampMixin, db.Model):
    __tablename__ = "project"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, index=True)
    description = db.Column(db.Text)

    owner_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )

    workspace_id = db.Column(
        db.Integer, db.ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=True, index=True
    )

    status = db.Column(db.String(20), default="active", nullable=False)
    priority = db.Column(db.String(20), default="medium", nullable=False)
    start_date = db.Column(db.Date)
    due_date = db.Column(db.Date)
    completed_at = db.Column(db.DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'on_hold', 'completed', 'archived')",
            name="valid_project_status"
        ),
        CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'urgent')",
            name="valid_project_priority"
        ),
    )

    owner = db.relationship("User", foreign_keys=[owner_id])

    workspace = db.relationship(
        "Workspace", back_populates="projects"
    )

    memberships = db.relationship(
        "ProjectMembership",
        back_populates="project",
        cascade="all, delete-orphan"
    )

    tasks = db.relationship(
        "Task",
        back_populates="project"
    )


class ProjectMembership(TimestampMixin, db.Model):
    __tablename__ = "project_membership"

    id = db.Column(db.Integer, primary_key=True)

    project_id = db.Column(
        db.Integer, db.ForeignKey("project.id", ondelete="CASCADE"),
        nullable=False
    )

    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False
    )

    role = db.Column(db.String(20), default="member", nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "project_id", "user_id",
            name="unique_project_membership"
        ),
        CheckConstraint(
            "role IN ('owner', 'manager', 'member', 'viewer')",
            name="valid_project_role"
        ),
    )

    project = db.relationship(
        "Project", back_populates="memberships"
    )

    user = db.relationship("User")


# ==================== TASKS ====================

class Task(TimestampMixin, db.Model):
    __tablename__ = "task"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, index=True)
    description = db.Column(db.Text)

    creator_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"),
        nullable=False, index=True
    )

    assignee_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True, index=True
    )

    project_id = db.Column(
        db.Integer, db.ForeignKey("project.id", ondelete="CASCADE"),
        nullable=True, index=True
    )

    parent_task_id = db.Column(
        db.Integer, db.ForeignKey("task.id", ondelete="SET NULL"),
        nullable=True
    )

    status = db.Column(db.String(20), default="todo", nullable=False)
    priority = db.Column(db.String(20), default="medium", nullable=False)
    due_at = db.Column(db.DateTime(timezone=True), index=True)
    completed_at = db.Column(db.DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('todo', 'in_progress', 'blocked', 'completed', 'cancelled')",
            name="valid_task_status"
        ),
        CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'urgent')",
            name="valid_task_priority"
        ),
    )

    creator = db.relationship(
        "User", foreign_keys=[creator_id]
    )

    assignee = db.relationship(
        "User", foreign_keys=[assignee_id]
    )

    project = db.relationship(
        "Project", back_populates="tasks"
    )

    parent_task = db.relationship(
        "Task",
        remote_side=[id],
        backref=db.backref("subtasks", lazy="select")
    )


# ==================== GOALS ====================

class Goal(TimestampMixin, db.Model):
    __tablename__ = "goal"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default="active", nullable=False)
    target_date = db.Column(db.Date)
    progress_percent = db.Column(db.Integer, default=0, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'completed', 'paused', 'cancelled')",
            name="valid_goal_status",
        ),
        CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="valid_goal_progress",
        ),
    )

    user = db.relationship(
        "User",
        backref=db.backref("goals", lazy="dynamic"),
    )

    milestones = db.relationship(
        "Milestone",
        back_populates="goal",
        cascade="all, delete-orphan",
    )


class Milestone(TimestampMixin, db.Model):
    __tablename__ = "milestone"

    id = db.Column(db.Integer, primary_key=True)

    goal_id = db.Column(
        db.Integer,
        db.ForeignKey("goal.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    due_date = db.Column(db.Date)
    is_completed = db.Column(db.Boolean, default=False, nullable=False)
    completed_at = db.Column(db.DateTime(timezone=True))

    goal = db.relationship("Goal", back_populates="milestones")


# ==================== NOTES ====================

class Note(TimestampMixin, db.Model):
    __tablename__ = "note"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False, default="")
    category = db.Column(db.String(80), index=True)
    tags = db.Column(db.JSON, nullable=False, default=list)
    is_pinned = db.Column(db.Boolean, default=False, nullable=False)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)

    user = db.relationship(
        "User",
        backref=db.backref("notes", lazy="dynamic"),
    )


# ==================== CALENDAR EVENTS ====================

class CalendarEvent(TimestampMixin, db.Model):
    __tablename__ = "calendar_event"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    starts_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    ends_at = db.Column(db.DateTime(timezone=True))
    timezone_name = db.Column(
        db.String(64),
        default="UTC",
        nullable=False,
    )
    location = db.Column(db.String(250))
    recurrence_rule = db.Column(db.String(500))
    is_all_day = db.Column(db.Boolean, default=False, nullable=False)

    user = db.relationship(
        "User",
        backref=db.backref("calendar_events", lazy="dynamic"),
    )


# ==================== REMINDERS ====================

class Reminder(TimestampMixin, db.Model):
    __tablename__ = "reminder"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    remind_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    related_type = db.Column(db.String(40))
    related_id = db.Column(db.Integer)
    status = db.Column(db.String(20), default="pending", nullable=False)
    delivered_at = db.Column(db.DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'delivered', 'cancelled')",
            name="valid_reminder_status",
        ),
    )

    user = db.relationship(
        "User",
        backref=db.backref("reminders", lazy="dynamic"),
    )


# ==================== FILE ASSETS ====================

class FileAsset(TimestampMixin, db.Model):
    __tablename__ = "file_asset"

    id = db.Column(db.Integer, primary_key=True)

    uploaded_by_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    original_filename = db.Column(db.String(255), nullable=False)
    storage_filename = db.Column(
        db.String(255),
        unique=True,
        nullable=False,
    )
    storage_path = db.Column(db.String(1000), nullable=False)
    mime_type = db.Column(db.String(150))
    size_bytes = db.Column(db.BigInteger, nullable=False)
    visibility = db.Column(
        db.String(20),
        default="private",
        nullable=False,
    )
    checksum_sha256 = db.Column(db.String(64))

    __table_args__ = (
        CheckConstraint(
            "size_bytes >= 0",
            name="valid_file_size",
        ),
        CheckConstraint(
            "visibility IN ('private', 'workspace', 'public')",
            name="valid_file_visibility",
        ),
    )

    uploaded_by = db.relationship(
        "User",
        foreign_keys=[uploaded_by_id],
    )


# ==================== ACTIVITY LOGS ====================

class ActivityLog(TimestampMixin, db.Model):
    __tablename__ = "activity_log"

    id = db.Column(db.Integer, primary_key=True)

    actor_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    workspace_id = db.Column(
        db.Integer,
        db.ForeignKey("workspace.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    action = db.Column(db.String(100), nullable=False, index=True)
    object_type = db.Column(db.String(80))
    object_id = db.Column(db.Integer)
    details = db.Column(db.JSON, nullable=False, default=dict)
    ip_address = db.Column(db.String(45))

    actor = db.relationship(
        "User",
        foreign_keys=[actor_id],
    )

    workspace = db.relationship(
        "Workspace",
        foreign_keys=[workspace_id],
    )
