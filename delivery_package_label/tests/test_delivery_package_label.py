# Copyright 2026 Jarsa
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import base64
from contextlib import contextmanager
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

ZPL = b"^XA^FDCARRIER^FS^XZ"


@tagged("post_install", "-at_install")
class TestDeliveryPackageLabel(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.warehouse.out_type_id.print_label = True
        cls.carrier = cls.env["delivery.carrier"].create(
            {
                "name": "Parcel Carrier",
                "delivery_type": "fixed",
                "product_id": cls.env["product.product"]
                .create({"name": "Shipping", "type": "service"})
                .id,
                "package_tracking_required": True,
            }
        )
        cls.products = cls.env["product.product"].create(
            [
                {"name": "Helmet", "is_storable": True},
                {"name": "Boots", "is_storable": True},
            ]
        )
        for product in cls.products:
            cls.env["stock.quant"]._update_available_quantity(
                product, cls.warehouse.lot_stock_id, 10
            )
        cls.customer = cls.env["res.partner"].create({"name": "Customer"})

    def setUp(self):
        super().setUp()
        self.calls = []
        self.fail_on = set()

    def _send_package(self, carrier, picking, package):
        self.calls.append(package.name)
        if package.name in self.fail_on:
            raise UserError(self.env._("Carrier down"))
        label = self.env["ir.attachment"].create(
            {
                "name": f"LabelShipping-{package.name}.zpl",
                "raw": ZPL,
                "res_model": "stock.picking",
                "res_id": picking.id,
            }
        )
        return {
            "tracking_number": f"TRK-{package.name}",
            "exact_price": 10.0,
            "attachment_ids": label,
        }

    @contextmanager
    def carrier_api(self, mode):
        test = self

        def send_package(carrier, picking, package):
            return test._send_package(carrier, picking, package)

        with patch.object(
            type(self.carrier), "fixed_send_package", send_package, create=True
        ):
            self.carrier.package_label_generation = mode
            yield

    def _delivery(self):
        picking_type = self.warehouse.out_type_id
        source = picking_type.default_location_src_id
        destination = picking_type.default_location_dest_id
        picking = self.env["stock.picking"].create(
            {
                "partner_id": self.customer.id,
                "picking_type_id": picking_type.id,
                "location_id": source.id,
                "location_dest_id": destination.id,
                "carrier_id": self.carrier.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "product_uom_qty": 2,
                            "location_id": source.id,
                            "location_dest_id": destination.id,
                        }
                    )
                    for product in self.products
                ],
            }
        )
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.picked = True
        return picking

    def _pack_each_line(self, picking):
        packages = self.env["stock.package"]
        for index, line in enumerate(picking.move_line_ids, start=1):
            package = self.env["stock.package"].create({"name": f"BOX-{index}"})
            line.result_package_id = package
            packages |= package
        return packages

    def test_mode_needs_carrier_support(self):
        self.assertFalse(self.carrier.package_label_support)
        with self.assertRaises(ValidationError):
            self.carrier.package_label_generation = "background"
        with self.carrier_api("background"):
            self.assertTrue(self.carrier.package_label_support)

    def test_on_demand_labels_then_validation(self):
        with self.carrier_api("on_demand"):
            picking = self._delivery()
            packages = self._pack_each_line(picking)
            self.assertTrue(picking.package_label_missing)
            picking.action_generate_package_labels()
            self.assertEqual(
                packages.mapped("carrier_tracking_ref"), ["TRK-BOX-1", "TRK-BOX-2"]
            )
            self.assertEqual(picking.carrier_tracking_ref, "TRK-BOX-1,TRK-BOX-2")
            self.assertEqual(picking.carrier_price, 20.0)
            self.assertFalse(picking.package_label_missing)
            picking.button_validate()
        self.assertEqual(picking.state, "done")
        self.assertEqual(self.calls, ["BOX-1", "BOX-2"])
        with self.assertRaisesRegex(UserError, "no package without carrier label"):
            picking.action_generate_package_labels()

    def test_on_demand_error_keeps_created_labels(self):
        with self.carrier_api("on_demand"):
            picking = self._delivery()
            packages = self._pack_each_line(picking)
            self.fail_on = {"BOX-2"}
            self.assertFalse(picking._generate_package_labels())
            self.assertEqual(packages[0].carrier_tracking_ref, "TRK-BOX-1")
            self.assertFalse(packages[1].carrier_tracking_ref)
            self.assertIn("BOX-2", picking.package_label_error)
            self.fail_on = set()
            picking.action_generate_package_labels()
        self.assertEqual(self.calls, ["BOX-1", "BOX-2", "BOX-2"])
        self.assertFalse(picking.package_label_error)

    def test_validation_creates_missing_labels(self):
        with self.carrier_api("on_demand"):
            picking = self._delivery()
            packages = self._pack_each_line(picking)
            picking.button_validate()
        self.assertEqual(picking.state, "done")
        self.assertTrue(all(packages.mapped("carrier_tracking_ref")))

    def test_first_label_error_blocks_validation(self):
        with self.carrier_api("on_demand"):
            picking = self._delivery()
            self._pack_each_line(picking)
            self.fail_on = {"BOX-1"}
            with self.assertRaisesRegex(UserError, "Carrier down"):
                picking.button_validate()

    def test_background_labels(self):
        with self.carrier_api("background"):
            picking = self._delivery()
            packages = self._pack_each_line(picking)
            picking.button_validate()
            self.assertEqual(picking.state, "done")
            self.assertTrue(picking.package_label_queued)
            self.assertFalse(self.calls)
            self.env["stock.picking"]._cron_generate_package_labels()
        self.assertFalse(picking.package_label_queued)
        self.assertTrue(all(packages.mapped("carrier_tracking_ref")))
        self.assertTrue(
            any(
                "every package" in (message.body or "")
                for message in picking.message_ids
            )
        )

    def test_background_error_schedules_activity(self):
        with self.carrier_api("background"):
            picking = self._delivery()
            packages = self._pack_each_line(picking)
            picking.button_validate()
            self.fail_on = {"BOX-2"}
            self.env["stock.picking"]._cron_generate_package_labels()
            self.assertFalse(picking.package_label_queued)
            self.assertTrue(picking.activity_ids)
            self.assertEqual(packages[0].carrier_tracking_ref, "TRK-BOX-1")
            self.fail_on = set()
            picking.action_generate_package_labels()
        self.assertTrue(all(packages.mapped("carrier_tracking_ref")))

    def test_pack_creates_and_downloads_labels(self):
        picking_type = self.warehouse.out_type_id
        picking_type.write(
            {"auto_print_package_label": True, "package_label_to_print": "zpl"}
        )
        with self.carrier_api("pack"):
            picking = self._delivery()
            action = (
                picking.move_line_ids[0]
                .with_context(from_package_wizard=True)
                .action_put_in_pack()
            )
        package = picking.move_line_ids.result_package_id
        self.assertEqual(len(package), 1)
        self.assertEqual(package.carrier_tracking_ref, f"TRK-{package.name}")
        self.assertEqual(action["type"], "ir.actions.act_url")
        printout = self.env["ir.attachment"].browse(
            int(action["url"].split("/")[3].split("?")[0])
        )
        content = base64.b64decode(printout.datas)
        self.assertTrue(content.endswith(ZPL))
        self.assertGreater(len(content), len(ZPL))

    def test_pack_error_keeps_the_package(self):
        with self.carrier_api("pack"):
            picking = self._delivery()
            with patch.object(
                type(self),
                "_send_package",
                side_effect=UserError(self.env._("Carrier down")),
            ):
                picking.move_line_ids[0].with_context(
                    from_package_wizard=True
                ).action_put_in_pack()
        self.assertTrue(picking.move_line_ids.result_package_id)
        self.assertIn("Carrier down", picking.package_label_error)

    def test_without_packages_one_label_for_the_delivery(self):
        with (
            self.carrier_api("background"),
            patch.object(
                type(self.carrier),
                "fixed_send_shipping",
                lambda carrier, pickings: [
                    {"exact_price": 5.0, "tracking_number": "ONE"}
                ],
                create=True,
            ),
        ):
            picking = self._delivery()
            picking.button_validate()
        self.assertEqual(picking.carrier_tracking_ref, "ONE")
        self.assertFalse(picking.package_label_queued)

    def test_manual_reference_not_required_with_labels(self):
        picking = self._delivery()
        self.assertTrue(picking.package_tracking_required)
        with self.carrier_api("background"):
            self.assertFalse(picking.package_tracking_required)
