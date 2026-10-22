import unittest

from app import app
from models import db, User
from extended_models import (
    Workspace,
    WorkspaceMembership,
    Project,
    ProjectMembership,
    Task,
    Note,
    Conversation,
    ConversationParticipant,
    Message,
)


class ProjectAccessSecurityTests(unittest.TestCase):
    def setUp(self):
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            SECRET_KEY="security-test-only-secret",
        )

        self.context = app.app_context()
        self.context.push()

        db.drop_all()
        db.create_all()

        self.client = app.test_client()

        self.owner = User(
            username="workspaceowner",
            email="owner@example.com",
        )
        self.owner.set_password("OwnerPass123")

        self.member = User(
            username="projectmember",
            email="member@example.com",
        )
        self.member.set_password("MemberPass123")

        self.other = User(
            username="otheruser",
            email="other@example.com",
        )
        self.other.set_password("OtherPass123")

        db.session.add_all([
            self.owner,
            self.member,
            self.other,
        ])
        db.session.flush()

        self.workspace = Workspace(
            name="Security Workspace",
            slug="security-workspace",
            description="Security tests",
            owner_id=self.owner.id,
            is_archived=False,
        )
        db.session.add(self.workspace)
        db.session.flush()

        db.session.add_all([
            WorkspaceMembership(
                workspace_id=self.workspace.id,
                user_id=self.owner.id,
                role="owner",
                status="active",
            ),
            WorkspaceMembership(
                workspace_id=self.workspace.id,
                user_id=self.member.id,
                role="member",
                status="suspended",
            ),
        ])

        self.project = Project(
            name="Private Project",
            description="Authorization test",
            owner_id=self.owner.id,
            workspace_id=self.workspace.id,
            status="active",
            priority="medium",
        )
        db.session.add(self.project)
        db.session.flush()

        db.session.add(ProjectMembership(
            project_id=self.project.id,
            user_id=self.member.id,
            role="manager",
        ))

        self.task = Task(
            title="Owner private task",
            description="Private task test",
            creator_id=self.owner.id,
            assignee_id=self.owner.id,
            status="todo",
            priority="medium",
        )

        self.note = Note(
            user_id=self.owner.id,
            title="Private owner note",
            content="Private note content",
        )

        self.conversation = Conversation(
            conversation_type="direct",
            title="Private conversation",
            created_by_id=self.owner.id,
            is_archived=False,
        )

        db.session.add_all([
            self.task,
            self.note,
            self.conversation,
        ])
        db.session.flush()

        db.session.add(ConversationParticipant(
            conversation_id=self.conversation.id,
            user_id=self.owner.id,
            is_muted=False,
        ))

        self.message = Message(
            conversation_id=self.conversation.id,
            sender_id=self.owner.id,
            body="Private message",
        )
        db.session.add(self.message)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def login(self, user):
        response = self.client.post(
            "/auth/login",
            data={
                "identity": user.username,
                "password": {
                    self.owner.id: "OwnerPass123",
                    self.member.id: "MemberPass123",
                    self.other.id: "OtherPass123",
                }[user.id],
            },
        )
        self.assertEqual(response.status_code, 302)

    def test_anonymous_user_cannot_access_project(self):
        response = self.client.get(
            f"/api/projects/{self.project.id}"
        )
        self.assertEqual(response.status_code, 302)

    def test_suspended_member_cannot_access_project(self):
        self.login(self.member)

        response = self.client.get(
            f"/api/projects/{self.project.id}"
        )
        self.assertEqual(response.status_code, 404)

    def test_other_user_cannot_read_private_task(self):
        self.login(self.other)

        response = self.client.get(
            f"/api/tasks/{self.task.id}"
        )
        self.assertEqual(response.status_code, 403)

    def test_other_user_cannot_modify_private_task(self):
        self.login(self.other)

        response = self.client.patch(
            f"/api/tasks/{self.task.id}",
            json={"title": "Unauthorized change"},
        )
        self.assertEqual(response.status_code, 403)

    def test_other_user_cannot_delete_private_task(self):
        self.login(self.other)

        response = self.client.delete(
            f"/api/tasks/{self.task.id}"
        )
        self.assertEqual(response.status_code, 403)

    def test_other_user_cannot_read_private_note(self):
        self.login(self.other)

        response = self.client.get(
            f"/api/notes/{self.note.id}"
        )
        self.assertEqual(response.status_code, 403)

    def test_other_user_cannot_modify_private_note(self):
        self.login(self.other)

        response = self.client.patch(
            f"/api/notes/{self.note.id}",
            json={"title": "Unauthorized note change"},
        )
        self.assertEqual(response.status_code, 403)

    def test_nonparticipant_cannot_read_conversation_messages(self):
        self.login(self.other)

        response = self.client.get(
            f"/api/conversations/{self.conversation.id}/messages"
        )
        self.assertEqual(response.status_code, 404)

    def test_nonparticipant_cannot_send_conversation_message(self):
        self.login(self.other)

        response = self.client.post(
            f"/api/conversations/{self.conversation.id}/messages",
            json={"body": "Unauthorized message"},
        )
        self.assertEqual(response.status_code, 404)

    def test_nonparticipant_cannot_edit_another_users_message(self):
        self.login(self.other)

        response = self.client.patch(
            f"/api/messages/{self.message.id}",
            json={"body": "Unauthorized edit"},
        )
        self.assertEqual(response.status_code, 404)

    def test_project_member_without_manager_role_cannot_update_project(self):
        # Turn the workspace membership active, then use a viewer role.
        membership = WorkspaceMembership.query.filter_by(
            workspace_id=self.workspace.id,
            user_id=self.member.id,
        ).first()
        membership.status = "active"

        project_membership = ProjectMembership.query.filter_by(
            project_id=self.project.id,
            user_id=self.member.id,
        ).first()
        project_membership.role = "viewer"
        db.session.commit()

        self.login(self.member)

        response = self.client.patch(
            f"/api/projects/{self.project.id}",
            json={"name": "Unauthorized project edit"},
        )
        self.assertEqual(response.status_code, 403)

    def test_message_sender_cannot_be_impersonated_by_nonparticipant(self):
        self.login(self.other)

        response = self.client.delete(
            f"/api/messages/{self.message.id}"
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)

    def test_archived_workspace_blocks_project_access(self):
        self.login(self.owner)
        self.workspace.is_archived = True
        db.session.commit()

        response = self.client.get(
            f"/api/projects/{self.project.id}"
        )
        self.assertEqual(response.status_code, 404)

    def test_viewer_cannot_create_project_task(self):
        membership = WorkspaceMembership.query.filter_by(
            workspace_id=self.workspace.id,
            user_id=self.member.id,
        ).first()
        membership.status = "active"

        project_membership = ProjectMembership.query.filter_by(
            project_id=self.project.id,
            user_id=self.member.id,
        ).first()
        project_membership.role = "viewer"
        db.session.commit()

        self.login(self.member)
        response = self.client.post(
            f"/api/projects/{self.project.id}/tasks",
            json={"title": "Unauthorized task"},
        )
        self.assertEqual(response.status_code, 403)

    def test_project_completion_timestamp_is_managed(self):
        self.login(self.owner)

        response = self.client.patch(
            f"/api/projects/{self.project.id}",
            json={"status": "completed"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(
            response.get_json()["project"]["completed_at"]
        )

        response = self.client.patch(
            f"/api/projects/{self.project.id}",
            json={"status": "active"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(
            response.get_json()["project"]["completed_at"]
        )
