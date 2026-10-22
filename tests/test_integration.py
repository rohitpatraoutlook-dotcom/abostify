import unittest

from app import app
from models import db, User
from extended_models import Project, Task


class AbostifyIntegrationTests(unittest.TestCase):

    def setUp(self):
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            SECRET_KEY="integration-test-only-secret",
        )

        self.app_context = app.app_context()
        self.app_context.push()

        db.drop_all()
        db.create_all()

        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def register_user(
        self,
        username="testuser",
        email="test@example.com",
        password="TestPass123",
    ):
        return self.client.post(
            "/auth/register",
            data={
                "username": username,
                "email": email,
                "password": password,
            },
            follow_redirects=False,
        )

    def login_user(
        self,
        identity="testuser",
        password="TestPass123",
    ):
        return self.client.post(
            "/auth/login",
            data={
                "identity": identity,
                "password": password,
            },
            follow_redirects=False,
        )

    def test_health_and_home(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "healthy")

        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_dashboard_requires_login(self):
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 302)

    def test_registration_creates_user_and_logs_in(self):
        response = self.register_user()

        self.assertEqual(response.status_code, 302)

        user = User.query.filter_by(
            username="testuser"
        ).first()

        self.assertIsNotNone(user)
        self.assertTrue(user.check_password("TestPass123"))

        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)

    def test_duplicate_registration_is_rejected(self):
        self.register_user()

        self.client.post(
            "/auth/logout",
            follow_redirects=False,
        )

        response = self.register_user()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            User.query.filter_by(username="testuser").count(),
            1,
        )

    def test_invalid_password_is_rejected(self):
        self.register_user()

        self.client.post("/auth/logout")

        response = self.login_user(
            password="WrongPassword123"
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            "user_id",
            self.client.get_cookie("session").value
            if self.client.get_cookie("session")
            else "",
        )

    def test_login_with_email(self):
        self.register_user()
        self.client.post("/auth/logout")

        response = self.login_user(
            identity="TEST@example.com"
        )

        self.assertEqual(response.status_code, 302)

        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)

    def test_workspace_api_requires_login(self):
        response = self.client.get("/api/workspaces")
        self.assertEqual(response.status_code, 302)

    def test_project_default_status_is_active(self):
        self.register_user()

        response = self.client.post(
            "/api/projects",
            json={"name": "Integration Project"},
        )

        self.assertEqual(response.status_code, 201)

        project = Project.query.filter_by(
            name="Integration Project"
        ).first()

        self.assertIsNotNone(project)
        self.assertEqual(project.status, "active")

    def test_cancelled_task_status_is_accepted(self):
        self.register_user()

        project_response = self.client.post(
            "/api/projects",
            json={"name": "Task Test Project"},
        )

        self.assertEqual(project_response.status_code, 201)

        project_id = project_response.json["project"]["id"]

        response = self.client.post(
            f"/api/projects/{project_id}/tasks",
            json={
                "title": "Cancelled task test",
                "status": "cancelled",
            },
        )

        self.assertEqual(response.status_code, 201)

        task = Task.query.filter_by(
            title="Cancelled task test"
        ).first()

        self.assertIsNotNone(task)
        self.assertEqual(task.status, "cancelled")


if __name__ == "__main__":
    unittest.main(verbosity=2)
