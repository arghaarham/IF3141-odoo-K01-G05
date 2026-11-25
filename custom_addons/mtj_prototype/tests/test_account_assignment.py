import secrets

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase


class TestAccountAssignment(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref("mtj_prototype.account_technical_admin").user_id
        cls.order_reviewer = cls.env.ref("mtj_prototype.account_reviewer_order")
        cls.stock_reviewer = cls.env.ref("mtj_prototype.account_reviewer_stock")
        cls.assignment = cls.env["mtj.account.assignment"].with_user(cls.admin)
        cls.audit = cls.env["mtj.audit.event"].with_user(cls.admin)

    def test_admin_manages_assignment_with_an_audit_trail(self):
        self.assertFalse(self.admin.has_group("base.group_system"))
        self.assertFalse(self.admin.has_group("base.group_erp_manager"))
        account = self.assignment.create({
            "name": "  Peninjau Baru ",
            "login": " MTJ.PENINJAU.BARU ",
            "role": "a05",
            "scope": "order",
        })
        user = account.user_id
        self.assertEqual(account.login, "mtj.peninjau.baru")
        self.assertEqual(account.name, "Peninjau Baru")
        self.assertTrue(account.active)
        self.assertTrue(user.has_group("mtj_prototype.group_mtj_reviewer_order"))

        account.write({"scope": "stock"})
        self.assertFalse(user.has_group("mtj_prototype.group_mtj_reviewer_order"))
        self.assertTrue(user.has_group("mtj_prototype.group_mtj_reviewer_stock"))
        self.assertTrue(user.has_group("mtj_prototype.group_mtj_reviewer"))
        account.action_archive()
        self.assertFalse(account.active)
        self.assertFalse(user.active)
        account.action_archive()

        action = account.action_view_audit()
        events = self.audit.search(action["domain"], order="id")
        self.assertEqual(len(events), 3)
        self.assertEqual(events.actor_id, self.admin)
        self.assertTrue(all(events.mapped("occurred_at")))
        self.assertEqual(events[1].old_values["scope"], "order")
        self.assertEqual(events[1].new_values["scope"], "stock")
        self.assertTrue(events[2].old_values["active"])
        self.assertFalse(events[2].new_values["active"])
        account.action_unarchive()
        self.assertTrue(user.active)
        self.assertEqual(len(self.audit.search(action["domain"])), 4)

    def test_rejects_invalid_assignment_and_direct_escalation(self):
        admin_assignment = self.order_reviewer.with_user(self.admin)
        with self.assertRaises(ValidationError):
            admin_assignment.write({"role": "a04"})
        user = self.order_reviewer.user_id
        self.assertTrue(user.has_group("mtj_prototype.group_mtj_reviewer_order"))
        self.assertFalse(user.has_group("mtj_prototype.group_mtj_reviewer_stock"))
        with self.assertRaises(AccessError):
            self.order_reviewer.with_user(user).read(["role"])
        with self.assertRaises(AccessError):
            self.order_reviewer.with_user(user).write({"role": "a06", "scope": "technical"})
        with self.assertRaises(AccessError):
            self.order_reviewer.with_user(user).action_set_password()
        with self.assertRaises(AccessError):
            user.with_user(user).write({
                "groups_id": [Command.link(self.env.ref("mtj_prototype.group_mtj_technical_admin").id)]
            })
        with self.assertRaises(AccessError):
            admin_assignment.write({"user_id": self.env.ref("base.user_admin").id})
        with self.assertRaises(AccessError):
            self.env["mtj.account.password"].with_user(user).create({
                "assignment_id": self.order_reviewer.id, "password": secrets.token_urlsafe(16),
            })

    def test_account_admin_menu_and_audit_scope(self):
        accounts_menu = self.env.ref("mtj_prototype.menu_mtj_accounts")
        self.assertIn(accounts_menu.id, accounts_menu.with_user(self.admin)._visible_menu_ids())
        for account in (self.order_reviewer, self.stock_reviewer):
            self.assertNotIn(
                accounts_menu.id, accounts_menu.with_user(account.user_id)._visible_menu_ids()
            )
        order_account_events = self.audit.search([
            ("res_model", "=", "mtj.account.assignment"), ("res_id", "=", self.order_reviewer.id),
        ])
        self.assertTrue(order_account_events)
        with self.assertRaises(AccessError):
            order_account_events.with_user(self.order_reviewer.user_id).read(["new_values"])
        with self.assertRaises(AccessError):
            order_account_events.write({"action": "Uji perubahan ilegal"})
        with self.assertRaises(AccessError):
            order_account_events.unlink()

        unrelated_event = self.env["mtj.audit.event"]._record(self.admin, "Catatan teknis lain")
        self.assertFalse(self.audit.search([("id", "=", unrelated_event.id)]))
        with self.assertRaises(AccessError):
            unrelated_event.with_user(self.admin).read(["new_values"])

    def test_wizard_does_not_store_password_or_allow_privileged_target(self):
        password_as_admin = self.env["mtj.account.password"].with_user(self.admin)
        account = self.order_reviewer
        password = secrets.token_urlsafe(16)
        wizard = password_as_admin.create({"assignment_id": account.id, "password": password})
        self.assertFalse(wizard.password)
        account.user_id.with_user(account.user_id)._check_credentials(password, {"interactive": True})

        account.user_id.sudo().write({
            "groups_id": [Command.link(self.env.ref("base.group_erp_manager").id)],
        })
        with self.assertRaises(AccessError):
            password_as_admin.create({"assignment_id": account.id, "password": password})
