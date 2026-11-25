from math import isfinite

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


def _normalize_code(value):
    return (value or "").strip().upper()


class Product(models.Model):
    _name = "mtj.product"
    _description = "Produk Uji"
    _order = "sku"
    _rec_names_search = ["sku", "name", "variant"]

    sku = fields.Char(string="SKU", required=True)
    name = fields.Char(string="Nama Produk", required=True)
    variant = fields.Char(string="Varian")
    uom_id = fields.Many2one(
        "uom.uom", string="Satuan Acuan", required=True, ondelete="restrict"
    )
    sample_price = fields.Float(string="Harga Contoh (Rp)", required=True, default=0)
    active = fields.Boolean(string="Aktif", default=True)

    _sql_constraints = [
        ("sku_unique", "UNIQUE(sku)", "SKU produk sudah digunakan."),
    ]

    @api.depends("sku", "name")
    def _compute_display_name(self):
        for product in self:
            product.display_name = f"[{product.sku}] {product.name}"

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([
            dict(values, sku=_normalize_code(values.get("sku"))) for values in vals_list
        ])

    def write(self, values):
        if "sku" in values:
            values = dict(values, sku=_normalize_code(values["sku"]))
        return super().write(values)

    @api.constrains("sku", "name", "uom_id", "sample_price")
    def _check_catalog_values(self):
        for product in self:
            if not product.sku or not product.name.strip():
                raise ValidationError(_("SKU dan nama produk wajib diisi."))
            if not product.uom_id.exists() or not product.uom_id.active:
                raise ValidationError(_("Satuan acuan harus menggunakan satuan Odoo yang aktif."))
            if not isfinite(product.sample_price) or product.sample_price < 0:
                raise ValidationError(_("Harga contoh harus berupa angka nonnegatif."))

    @api.constrains("uom_id")
    def _check_mapping_reference_unit(self):
        for product in self:
            if self.env["mtj.uom.mapping"].with_context(active_test=True).search_count([
                ("product_id", "=", product.id),
                ("active", "=", True),
                ("reference_uom_id", "!=", product.uom_id.id),
            ]):
                raise ValidationError(_("Arsipkan pemetaan aktif sebelum mengganti satuan acuan."))

    def _check_available_for_new_transaction(self):
        """Validate a newly selected product on the caller's transaction."""
        self.check_access_rights("read")
        self.check_access_rule("read")
        if self.exists() != self or any(not product.active for product in self):
            raise ValidationError(_("Pilih produk yang masih aktif untuk transaksi baru."))


class UomMapping(models.Model):
    _name = "mtj.uom.mapping"
    _description = "Pemetaan Satuan Uji"
    _order = "source, source_code, id"
    _rec_name = "source_code"

    source = fields.Selection(
        [("ketoko", "Ketoko (Uji)"), ("marketplace", "Marketplace (Uji)")],
        string="Sumber",
        required=True,
    )
    source_code = fields.Char(string="Kode Produk Sumber", required=True)
    source_uom_id = fields.Many2one(
        "uom.uom", string="Satuan Sumber", required=True, ondelete="restrict"
    )
    product_id = fields.Many2one(
        "mtj.product", string="Produk Acuan", required=True, ondelete="restrict", index=True
    )
    reference_uom_id = fields.Many2one(
        "uom.uom", string="Satuan Acuan", required=True, ondelete="restrict"
    )
    factor = fields.Float(string="Faktor Konversi", required=True)
    approval_basis = fields.Text(string="Dasar Persetujuan", required=True)
    active = fields.Boolean(string="Aktif", default=True)

    def init(self):
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS mtj_uom_mapping_active_source_uniq
            ON mtj_uom_mapping (source, source_code, source_uom_id)
            WHERE active
        """)

    @api.onchange("product_id")
    def _onchange_product_id(self):
        self.reference_uom_id = self.product_id.uom_id

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([
            dict(values, source_code=_normalize_code(values.get("source_code")))
            for values in vals_list
        ])

    def write(self, values):
        if "source_code" in values:
            values = dict(values, source_code=_normalize_code(values["source_code"]))
        return super().write(values)

    @api.constrains(
        "source_code", "source_uom_id", "product_id", "reference_uom_id",
        "factor", "approval_basis", "active",
    )
    def _check_mapping_values(self):
        for mapping in self:
            if not mapping.source_code or not (mapping.approval_basis or "").strip():
                raise ValidationError(_("Kode sumber dan dasar persetujuan wajib diisi."))
            if not isfinite(mapping.factor) or mapping.factor <= 0:
                raise ValidationError(_("Faktor konversi harus berupa angka berhingga di atas nol."))
            if not mapping.active:
                continue
            mapping.product_id._check_available_for_new_transaction()
            for unit in (mapping.source_uom_id, mapping.reference_uom_id):
                if not unit.exists() or not unit.active:
                    raise ValidationError(_("Satuan sumber dan acuan harus menggunakan satuan Odoo yang aktif."))
            if mapping.reference_uom_id != mapping.product_id.uom_id:
                raise ValidationError(_("Satuan acuan pemetaan harus sama dengan satuan acuan produk."))

    @api.model
    def _find_approved(self, source, source_code, source_uom):
        """Return the active approved mapping for one normalized source key."""
        source_uom.ensure_one()
        mapping = self.search([
            ("source", "=", source),
            ("source_code", "=", _normalize_code(source_code)),
            ("source_uom_id", "=", source_uom.id),
            ("source_uom_id.active", "=", True),
            ("reference_uom_id.active", "=", True),
            ("product_id.active", "=", True),
            ("active", "=", True),
        ], limit=1)
        return mapping.filtered(lambda rule: rule.reference_uom_id == rule.product_id.uom_id)
