from psycopg2.errors import UniqueViolation

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase


class TestMasterData(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref("mtj_prototype.account_technical_admin").user_id
        cls.order_reviewer = cls.env.ref("mtj_prototype.account_reviewer_order").user_id
        cls.stock_reviewer = cls.env.ref("mtj_prototype.account_reviewer_stock").user_id
        cls.products = cls.env["mtj.product"].with_user(cls.admin)
        cls.product = cls.env.ref("mtj_prototype.product_zp_01").with_user(cls.admin)
        cls.pcs = cls.env.ref("mtj_prototype.uom_pcs")
        cls.pack = cls.env.ref("mtj_prototype.uom_pack")
        cls.mapping = cls.env.ref("mtj_prototype.mapping_zp_01_pack").with_user(cls.admin)

    def test_product_validation_and_archive(self):
        product = self.products.create({
            "sku": "  barang-uji ",
            "name": "Barang Uji",
            "uom_id": self.pcs.id,
            "sample_price": 12.5,
        })
        self.assertEqual(product.sku, "BARANG-UJI")
        with self.assertRaises(UniqueViolation), self.cr.savepoint():
            product.write({"sku": "  zp-01 "})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            product.write({"sample_price": -1})

        unused_uom = self.env.ref("mtj_prototype.uom_roll")
        unused_uom.active = False
        with self.assertRaises(ValidationError), self.cr.savepoint():
            product.write({"uom_id": unused_uom.id})

        product.with_user(self.order_reviewer)._check_available_for_new_transaction()
        product.action_archive()
        self.assertFalse(self.products.search([("id", "=", product.id)]))
        self.assertEqual(product.with_user(self.order_reviewer).read(["sku"])[0]["sku"], "BARANG-UJI")
        with self.assertRaises(ValidationError):
            product.with_user(self.order_reviewer)._check_available_for_new_transaction()
        with self.assertRaises(AccessError):
            self.product.with_user(self.order_reviewer).write({"sample_price": 1000})

    def test_mapping_approval_lookup_and_scope(self):
        stock_mappings = self.env["mtj.uom.mapping"].with_user(self.stock_reviewer)
        lookup = (self.mapping.source, " zp-01 ", self.pack)
        self.assertFalse(stock_mappings._find_approved(*lookup))
        for values in ({"factor": 0}, {"factor": float("inf")}, {"approval_basis": "  "}):
            with self.assertRaises(ValidationError), self.cr.savepoint():
                self.mapping.write(values)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.mapping.write({"reference_uom_id": self.pack.id, "active": True})

        self.mapping.action_unarchive()
        result = stock_mappings._find_approved(*lookup)
        self.assertEqual(result.id, self.mapping.id)
        self.assertEqual(3 * result.factor, 30)
        with self.assertRaises(AccessError):
            self.mapping.with_user(self.stock_reviewer).write({"factor": 9})
        with self.assertRaises(AccessError):
            self.mapping.with_user(self.order_reviewer).read(["factor"])
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.product.write({"uom_id": self.pack.id})

        with self.assertRaises(UniqueViolation), self.cr.savepoint():
            self.mapping.copy({"source_code": " zp-01 "})

        self.product.action_archive()
        self.assertFalse(stock_mappings._find_approved(*lookup))
        self.assertEqual(result.product_id.sku, "ZP-01")
        self.mapping.action_archive()
        self.assertFalse(stock_mappings._find_approved(*lookup))

    def test_workspace_exposes_reference_menu_but_not_catalog_management(self):
        menus = self.env["ir.ui.menu"].with_user(self.order_reviewer)._visible_menu_ids()
        self.assertIn(self.env.ref("mtj_prototype.menu_mtj_root").id, menus)
        self.assertIn(self.env.ref("mtj_prototype.menu_mtj_product_reference").id, menus)
        self.assertNotIn(self.env.ref("mtj_prototype.menu_mtj_catalog").id, menus)
