# Copyright 2026 Jarsa
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    package_label_generation = fields.Selection(
        [
            ("validate", "On validation"),
            ("on_demand", "On demand, when the delivery is ready"),
            ("background", "In background, after validation"),
            ("pack", "When each package is packed"),
        ],
        string="Carrier Labels",
        default="validate",
        required=True,
        help="When the carrier labels of a delivery are created.\n"
        "On validation: the standard flow, every label when the delivery is "
        "validated.\n"
        "On demand: a button creates the labels of the packages once the "
        "delivery is ready; validation creates the missing ones.\n"
        "In background: validation is immediate and a scheduled action creates "
        "one label per package, for deliveries with many packages.\n"
        "When each package is packed: the label of each package is created and "
        "printed when the package is packed.\n"
        "Except on validation, the carrier integration must create labels per "
        "package.",
    )
    package_label_support = fields.Boolean(
        compute="_compute_package_label_support",
        help="The carrier integration creates one label per package.",
    )

    @api.depends("delivery_type")
    def _compute_package_label_support(self):
        for carrier in self:
            carrier.package_label_support = hasattr(
                carrier, f"{carrier.delivery_type}_send_package"
            )

    @api.constrains("package_label_generation", "delivery_type")
    def _check_package_label_generation(self):
        for carrier in self:
            if (
                carrier.package_label_generation != "validate"
                and not carrier.package_label_support
            ):
                raise ValidationError(
                    self.env._(
                        "%(carrier)s cannot create one label per package: keep its "
                        "carrier labels on validation.",
                        carrier=carrier.name,
                    )
                )

    def send_package(self, picking, package):
        """Create the carrier label of one package of a delivery.

        Carrier integrations implement ``<delivery_type>_send_package(picking,
        package)`` returning a dict with ``tracking_number``, ``exact_price``
        and ``attachment_ids`` (the label attachments, to print them)."""
        self.ensure_one()
        return getattr(self, f"{self.delivery_type}_send_package")(picking, package)
