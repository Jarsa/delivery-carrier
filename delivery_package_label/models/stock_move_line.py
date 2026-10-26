# Copyright 2026 Jarsa
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import models
from odoo.exceptions import UserError


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def _post_put_in_pack_hook(self, package):
        picking = self.picking_id[:1]
        if not (
            package
            and picking.picking_type_code == "outgoing"
            and picking.carrier_id.package_label_generation == "pack"
            and picking.carrier_id.integration_level == "rate_and_ship"
        ):
            return super()._post_put_in_pack_hook(package)
        action = super()._post_put_in_pack_hook(package)
        try:
            with self.env.cr.savepoint():
                attachments = picking._generate_package_label(package)
        except UserError as error:
            # the package stays packed: the label is created on validation or
            # with the button
            picking.package_label_error = self.env._(
                "Package %(package)s: %(error)s",
                package=package.name,
                error=error.args[0],
            )
            picking.message_post(body=picking.package_label_error)
            return action
        return picking._package_label_print_action(package, attachments, action)
