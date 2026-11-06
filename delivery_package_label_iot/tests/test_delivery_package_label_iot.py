# Copyright 2026 Jarsa
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import base64
from unittest.mock import patch

from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

ZPL = b"^XA^FDCARRIER^FS^XZ"


@tagged("post_install", "-at_install")
class TestDeliveryPackageLabelIot(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.picking_type = (
            cls.env["stock.warehouse"]
            .search([("company_id", "=", cls.env.company.id)], limit=1)
            .out_type_id
        )
        cls.carrier = cls.env["delivery.carrier"].create(
            {
                "name": "Parcel Carrier",
                "delivery_type": "fixed",
                "product_id": cls.env["product.product"]
                .create({"name": "Shipping", "type": "service"})
                .id,
            }
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Helmet", "is_storable": True}
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, cls.picking_type.default_location_src_id, 10
        )
        box = cls.env["iot.box"].create({"name": "Box", "identifier": "box-1"})
        cls.printer = cls.env["iot.device"].create(
            {
                "iot_id": box.id,
                "name": "Zebra",
                "identifier": "zebra-1",
                "type": "printer",
            }
        )
        cls.package_report = cls.env.ref(
            "delivery_package_label_iot.action_report_package_labels"
        )
        cls.picking_report = cls.env.ref("delivery_iot.action_report_shipping_labels")

    def setUp(self):
        super().setUp()

        def send_package(carrier, picking, package):
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

        patcher = patch.object(
            type(self.carrier), "fixed_send_package", send_package, create=True
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _delivery(self, mode):
        self.carrier.package_label_generation = mode
        source = self.picking_type.default_location_src_id
        destination = self.picking_type.default_location_dest_id
        picking = self.env["stock.picking"].create(
            {
                "partner_id": self.env.company.partner_id.id,
                "picking_type_id": self.picking_type.id,
                "location_id": source.id,
                "location_dest_id": destination.id,
                "carrier_id": self.carrier.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 2,
                            "location_id": source.id,
                            "location_dest_id": destination.id,
                        }
                    )
                ],
            }
        )
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.picked = True
        return picking

    def _put_in_pack(self, picking):
        action = picking.move_line_ids.with_context(
            from_package_wizard=True
        ).action_put_in_pack()
        return picking.move_line_ids.result_package_id, action

    def test_label_when_packed_goes_to_the_printer(self):
        self.package_report.device_ids = self.printer
        picking = self._delivery("pack")
        package, action = self._put_in_pack(picking)
        self.assertEqual(package.carrier_tracking_ref, f"TRK-{package.name}")
        self.assertEqual(action["type"], "ir.actions.report")
        self.assertEqual(action["device_ids"], [self.printer.identifier])
        self.assertEqual(action["context"]["active_ids"], package.ids)
        jobs = self.package_report.render_document(self.printer.ids, package.ids)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["deviceIdentifier"], self.printer.identifier)
        self.assertEqual(base64.b64decode(jobs[0]["document"]), ZPL)

    def test_without_printer_the_file_is_downloaded(self):
        picking = self._delivery("pack")
        action = self._put_in_pack(picking)[1]
        self.assertEqual(action["type"], "ir.actions.act_url")

    def test_labels_on_demand_go_to_the_printer(self):
        self.picking_report.device_ids = self.printer
        self.picking_type.auto_print_carrier_labels = True
        picking = self._delivery("on_demand")
        self._put_in_pack(picking)
        action = picking.action_generate_package_labels()
        self.assertEqual(action["type"], "ir.actions.report")
        self.assertEqual(action["device_ids"], [self.printer.identifier])
        self.assertEqual(action["context"]["active_ids"], picking.ids)
        self.picking_type.auto_print_carrier_labels = False
        picking = self._delivery("on_demand")
        self._put_in_pack(picking)
        self.assertIs(picking.action_generate_package_labels(), True)
