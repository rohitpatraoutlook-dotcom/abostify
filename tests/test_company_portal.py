import unittest

from app import app
from models import db, User
from company_portal import Company, CompanyEmployee, CompanyJoinRequest


class CompanyPortalTests(unittest.TestCase):
    def setUp(self):
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            SECRET_KEY="company-portal-test-secret",
        )
        self.context = app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def register(self, username, email):
        return self.client.post(
            "/auth/register",
            data={
                "username": username,
                "email": email,
                "password": "TestPass123",
            },
            follow_redirects=False,
        )

    def login(self, username):
        return self.client.post(
            "/auth/login",
            data={
                "identity": username,
                "password": "TestPass123",
            },
            follow_redirects=False,
        )

    def logout(self):
        return self.client.post("/auth/logout", follow_redirects=False)

    def create_company_as_owner(self):
        response = self.client.post(
            "/companies/register",
            data={
                "name": "Northstar Software",
                "industry": "Technology",
                "location": "Bengaluru",
                "description": "A test company",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        return Company.query.filter_by(name="Northstar Software").first()

    def test_company_registration_creates_owner_and_workspace(self):
        self.register("companyowner", "owner@example.com")
        company = self.create_company_as_owner()

        self.assertIsNotNone(company)
        self.assertIsNotNone(company.workspace_id)
        self.assertEqual(company.owner.username, "companyowner")

        owner_membership = CompanyEmployee.query.filter_by(
            company_id=company.id,
            user_id=company.owner_id,
        ).first()

        self.assertIsNotNone(owner_membership)
        self.assertEqual(owner_membership.role, "owner")

    def test_join_request_requires_approval_and_owner_can_approve(self):
        self.register("companyowner", "owner@example.com")
        company = self.create_company_as_owner()
        self.logout()

        self.register("jobseeker", "jobseeker@example.com")
        response = self.client.post(
            f"/companies/{company.id}/join",
            data={"message": "I would like to join the team."},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        join_request = CompanyJoinRequest.query.filter_by(
            company_id=company.id,
            user_id=User.query.filter_by(username="jobseeker").first().id,
        ).first()

        self.assertIsNotNone(join_request)
        self.assertEqual(join_request.status, "pending")
        self.assertIsNone(CompanyEmployee.query.filter_by(
            company_id=company.id,
            user_id=join_request.user_id,
        ).first())

        self.logout()
        self.login("companyowner")

        response = self.client.post(
            f"/companies/{company.id}/requests/{join_request.id}/review",
            data={
                "decision": "approve",
                "role": "hr",
                "designation": "HR Executive",
                "department": "Human Resources",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        db.session.expire_all()
        self.assertEqual(
            db.session.get(CompanyJoinRequest, join_request.id).status,
            "approved",
        )
        employee = CompanyEmployee.query.filter_by(
            company_id=company.id,
            user_id=join_request.user_id,
        ).first()
        self.assertIsNotNone(employee)
        self.assertEqual(employee.role, "hr")
        self.assertEqual(employee.designation, "HR Executive")
        self.assertEqual(employee.department, "Human Resources")

    def test_non_hr_cannot_approve_join_request(self):
        self.register("companyowner", "owner@example.com")
        company = self.create_company_as_owner()
        self.logout()

        self.register("jobseeker", "jobseeker@example.com")
        self.client.post(
            f"/companies/{company.id}/join",
            data={"message": "Please consider my request."},
        )
        join_request = CompanyJoinRequest.query.filter_by(
            company_id=company.id
        ).first()

        self.logout()
        self.register("outsider", "outsider@example.com")
        response = self.client.post(
            f"/companies/{company.id}/requests/{join_request.id}/review",
            data={"decision": "approve", "role": "admin"},
        )

        self.assertEqual(response.status_code, 403)
        db.session.expire_all()
        self.assertEqual(
            db.session.get(CompanyJoinRequest, join_request.id).status,
            "pending",
        )

    def test_company_pages_require_login(self):
        response = self.client.get("/companies")
        self.assertEqual(response.status_code, 302)

    def test_company_registration_rejects_short_name(self):
        self.register("companyowner", "owner@example.com")
        response = self.client.post(
            "/companies/register",
            data={"name": "AB"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Company.query.count(), 0)


if __name__ == "__main__":
    unittest.main()
