from odoo import api, fields, models


class AuditEvent(models.Model):
    _name = "mtj.audit.event"
    _description = "Riwayat Perubahan"
    _order = "occurred_at desc, id desc"

    res_model = fields.Char(string="Model Objek", required=True, readonly=True)
    res_id = fields.Integer(string="ID Objek", required=True, readonly=True)
    actor_id = fields.Many2one(
        "res.users", string="Pelaku", required=True, readonly=True, ondelete="restrict"
    )
    occurred_at = fields.Datetime(string="Waktu", required=True, readonly=True)
    action = fields.Char(string="Tindakan", required=True, readonly=True)
    old_values = fields.Json(string="Nilai Sebelumnya", readonly=True)
    new_values = fields.Json(string="Nilai Terbaru", readonly=True)
    reason = fields.Text(string="Alasan", readonly=True)

    @api.model
    def _record(self, record, action, *, old_values=None, new_values=None, reason=None):
        """Append an event from an already authorized business action."""
        record.ensure_one()
        return self.sudo().with_context({}).create({
            "res_model": record._name,
            "res_id": record.id,
            "actor_id": self.env.uid,
            "occurred_at": fields.Datetime.now(),
            "action": action,
            "old_values": old_values or {},
            "new_values": new_values or {},
            "reason": reason,
        })
