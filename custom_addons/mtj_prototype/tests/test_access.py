import json
import secrets

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestMtjLogin(HttpCase):

    def _authenticate(self, login, password):
        self.opener.cookies.clear()
        response = self.url_open(
            "/web/session/authenticate",
            data=json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "params": {"db": self.env.cr.dbname, "login": login, "password": password},
            }),
            headers={"Content-Type": "application/json"},
        ).json()
        return response

    def test_native_login_and_inactive_account(self):
        app_admin = self.env.ref("mtj_prototype.account_technical_admin")
        recorder = self.env.ref("mtj_prototype.account_order_recorder")
        stock_reviewer = self.env.ref("mtj_prototype.account_reviewer_stock")
        wizard = self.env["mtj.account.password"].with_user(app_admin.user_id)
        password = secrets.token_urlsafe(16)

        self.assertIn("error", self._authenticate(recorder.login, password))
        for account in (recorder, stock_reviewer):
            wizard.create({"assignment_id": account.id, "password": password})
            response = self._authenticate(account.login, password)
            self.assertEqual(response.get("result", {}).get("uid"), account.user_id.id, response)

        self.assertIn("error", self._authenticate(recorder.login, "sandi-uji-yang-salah"))
        recorder.with_user(app_admin.user_id).action_archive()
        self.assertIn("error", self._authenticate(recorder.login, password))
