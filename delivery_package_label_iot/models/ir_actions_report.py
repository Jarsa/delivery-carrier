# Copyright 2026 Jarsa
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import models

REPORT = "delivery_package_label_iot.report_package_labels"


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    def render_document(self, device_id_list, res_ids, data=None):
        """The file ``delivery_package_label`` made to print for each package
        (package label of the operation type followed by the carrier labels),
        the latest one of each package."""
        if self.report_name != REPORT:
            return super().render_document(device_id_list, res_ids, data)
        devices = self.env["iot.device"].browse(device_id_list).exists()
        attachments = self.env["ir.attachment"].search(
            [
                ("res_model", "=", "stock.package"),
                ("res_id", "in", res_ids),
                ("name", "like", "Labels-%"),
            ],
            order="id desc",
        )
        seen = set()
        latest = attachments.filtered(
            lambda a: a.res_id not in seen and not seen.add(a.res_id)
        )
        return [
            {
                "iotBoxId": device.iot_id.id,
                "deviceId": device.id,
                "deviceIdentifier": device.identifier,
                "deviceName": device.display_name,
                "document": attachment.datas,
            }
            for attachment in latest
            for device in devices
        ]
