from odoo import _, api, Command, fields, models
from odoo.exceptions import AccessError, ValidationError


ROLES = [
    ("a01", "A-01 · Pencatat Pesanan"),
    ("a02", "A-02 · Pemeriksa Pembayaran"),
    ("a03", "A-03 · Petugas Pemenuhan"),
    ("a04", "A-04 · Petugas Persediaan"),
    ("a05", "A-05 · Koordinator atau Peninjau"),
    ("a06", "A-06 · Administrator Teknis Uji"),
]
SCOPES = [
    ("order", "Pesanan"),
    ("stock", "Persediaan"),
    ("technical", "Teknis"),
]
ROLE_GROUPS = {
    ("a01", "order"): "group_mtj_order_recorder",
    ("a02", "order"): "group_mtj_payment_reviewer",
    ("a03", "order"): "group_mtj_fulfillment",
    ("a04", "stock"): "group_mtj_stock_operator",
    ("a05", "order"): "group_mtj_reviewer_order",
    ("a05", "stock"): "group_mtj_reviewer_stock",
    ("a06", "technical"): "group_mtj_technical_admin",
}
ADMIN_GROUP = "mtj_prototype.group_mtj_technical_admin"
ACCOUNT_FIELDS = {"name", "login", "active", "role", "scope"}


class AccountAssignment(models.Model):
    _name = "mtj.account.assignment"
    _description = "Akun dan Penugasan"
    _order = "name, id"

    user_id = fields.Many2one("res.users", required=True, readonly=True, ondelete="restrict")
    name = fields.Char(string="Nama", related="user_id.name", store=True, readonly=False)
    login = fields.Char(string="Nama Login", related="user_id.login", store=True, readonly=False)
    active = fields.Boolean(string="Aktif", related="user_id.active", store=True, readonly=False)
    role = fields.Selection(ROLES, string="Peran", required=True)
    scope = fields.Selection(SCOPES, string="Lingkup", required=True)

    _sql_constraints = [
        ("user_unique", "UNIQUE(user_id)", "Akun uji sudah memiliki penugasan."),
    ]

    @api.model
    def _check_admin(self):
        if not self.env.is_superuser() and not self.env.user.has_group(ADMIN_GROUP):
            raise AccessError(_("Pengelolaan akun memerlukan Administrator Teknis Uji."))

    @api.model
    def _group_for(self, role, scope):
        group = ROLE_GROUPS.get((role, scope))
        if not group:
            raise ValidationError(_("Lingkup penugasan tidak sesuai dengan peran."))
        return self.env.ref(f"mtj_prototype.{group}")

    @api.model
    def _check_account_fields(self, values):
        if values.keys() - ACCOUNT_FIELDS:
            raise AccessError(_("Hanya identitas, status, peran, dan lingkup akun uji yang dapat diubah."))

    @api.model
    def _user_values(self, values):
        user_values = {key: values[key] for key in ("name", "login", "active") if key in values}
        for key in ("name", "login"):
            if key in user_values:
                user_values[key] = (user_values[key] or "").strip()
                if not user_values[key]:
                    raise ValidationError(_("Nama dan nama login wajib diisi."))
        if "login" in user_values:
            user_values["login"] = user_values["login"].lower()
        return user_values

    def _managed_user(self):
        self.ensure_one()
        user = self.user_id.sudo().with_context({}, no_reset_password=True)
        workspace_group = self.env.ref("mtj_prototype.group_mtj_user").sudo()
        allowed_groups = workspace_group | workspace_group.trans_implied_ids
        allowed_groups |= self.env.ref("mtj_prototype.group_mtj_reviewer").sudo()
        for group in ROLE_GROUPS.values():
            allowed_groups |= self.env.ref(f"mtj_prototype.{group}").sudo()
        if user.groups_id - allowed_groups:
            raise AccessError(_("Akun dengan hak akses di luar prototipe harus dikelola di Pengaturan Odoo."))
        return user

    def _audit_values(self):
        self.ensure_one()
        return {"role": self.role, "scope": self.scope, "active": self.active}

    @api.model_create_multi
    def create(self, vals_list):
        self._check_admin()
        self.check_access_rights("create")
        users = self.env["res.users"].sudo().with_context({}, no_reset_password=True)
        assignment_values = []
        for values in vals_list:
            self._check_account_fields(values)
            role, scope = values.get("role"), values.get("scope")
            group = self._group_for(role, scope)
            user_values = self._user_values(values)
            if not user_values.get("name") or not user_values.get("login"):
                raise ValidationError(_("Nama dan nama login wajib diisi."))
            user = users.create({
                "active": True,
                **user_values,
                "groups_id": [Command.set([group.id])],
                "tz": "Asia/Jakarta",
            })
            assignment_values.append({"user_id": user.id, "role": role, "scope": scope})
        assignments = super(AccountAssignment, self.with_context({})).create(assignment_values)
        for assignment in assignments:
            self.env["mtj.audit.event"]._record(
                assignment, "Buat akun uji", new_values=assignment._audit_values()
            )
        return assignments

    def write(self, values):
        self._check_admin()
        self.check_access_rights("write")
        self.check_access_rule("write")
        self._check_account_fields(values)
        user_values = self._user_values(values)
        role_values = {key: values[key] for key in ("role", "scope") if key in values}
        for assignment in self:
            user = assignment._managed_user()
            before = assignment._audit_values()
            group = self._group_for(
                role_values.get("role", assignment.role),
                role_values.get("scope", assignment.scope),
            )
            if role_values:
                super(AccountAssignment, assignment).write(role_values)
            if role_values or user_values:
                updates = dict(user_values)
                if role_values:
                    updates["groups_id"] = [Command.set([group.id])]
                user.write(updates)
            after = assignment._audit_values()
            if before != after:
                self.env["mtj.audit.event"]._record(
                    assignment, "Ubah penugasan akun", old_values=before, new_values=after
                )
        return True

    def _check_admin_write(self):
        self.ensure_one()
        self._check_admin()
        self.check_access_rights("write")
        self.check_access_rule("write")

    def action_set_password(self):
        self._check_admin_write()
        return {
            "type": "ir.actions.act_window",
            "name": _("Atur Kata Sandi"),
            "res_model": "mtj.account.password",
            "view_mode": "form",
            "target": "new",
            "context": {"default_assignment_id": self.id},
        }

    def action_view_audit(self):
        self.ensure_one()
        self._check_admin()
        self.check_access_rights("read")
        self.check_access_rule("read")
        action = self.env["ir.actions.actions"]._for_xml_id("mtj_prototype.action_mtj_account_audit")
        action["domain"] = [("res_model", "=", self._name), ("res_id", "=", self.id)]
        return action


class AccountPassword(models.TransientModel):
    _name = "mtj.account.password"
    _description = "Atur Kata Sandi Akun Uji"

    assignment_id = fields.Many2one(
        "mtj.account.assignment", string="Akun Uji", required=True, ondelete="cascade"
    )
    password = fields.Char(string="Kata Sandi Baru", store=False)

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access_rights("create")
        wizard_values = []
        for values in vals_list:
            assignment = self.env["mtj.account.assignment"].browse(values.get("assignment_id")).exists()
            password = values.get("password")
            if not assignment or not password or not password.strip():
                raise ValidationError(_("Pilih akun uji dan isi kata sandi baru."))
            assignment._check_admin_write()
            assignment._managed_user().write({"password": password})
            wizard_values.append({"assignment_id": assignment.id})
        return super().create(wizard_values)
