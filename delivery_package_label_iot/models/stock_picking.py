# Copyright 2026 Jarsa
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _package_label_print_action(self, package, attachments, package_action):
        """Send the labels of the package to the IoT printer of the report
        *Package Carrier Labels* instead of downloading them."""
        action = super()._package_label_print_action(
            package, attachments, package_action
        )
        report = self.env.ref("delivery_package_label_iot.action_report_package_labels")
        if not attachments or not report.device_ids:
            return action
        return report.report_action(package.ids, config=False)

    def action_generate_package_labels(self):
        """Labels created on demand are printed on the IoT printer of
        *Shipping Labels* (delivery_iot) when the operation type prints the
        carrier labels automatically."""
        result = super().action_generate_package_labels()
        report = self.env.ref("delivery_iot.action_report_shipping_labels")
        to_print = self.filtered(
            lambda p: p.picking_type_id.auto_print_carrier_labels
            and not p.package_label_error
        )
        if not to_print or not report.device_ids:
            return result
        return report.report_action(to_print.ids, config=False)
