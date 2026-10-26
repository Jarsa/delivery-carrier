# Copyright 2026 Jarsa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
import base64

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.pdf import merge_pdf


class StockPicking(models.Model):
    _inherit = "stock.picking"

    package_label_generation = fields.Selection(
        related="carrier_id.package_label_generation"
    )
    package_label_queued = fields.Boolean(
        copy=False,
        index=True,
        help="The carrier labels of the packages are being created in background.",
    )
    package_label_error = fields.Text(copy=False, readonly=True)
    package_label_missing = fields.Boolean(compute="_compute_package_label_missing")
    # labels created by the carrier integration replace the manual reference
    package_tracking_required = fields.Boolean(
        related=False, compute="_compute_package_tracking_required"
    )

    @api.depends(
        "carrier_id.package_tracking_required",
        "carrier_id.package_label_generation",
        "carrier_id.integration_level",
    )
    def _compute_package_tracking_required(self):
        for picking in self:
            picking.package_tracking_required = (
                picking.carrier_id.package_tracking_required
                and not picking._package_label_ready()
            )

    @api.depends(
        "move_line_ids.result_package_id.carrier_tracking_ref", "package_label_queued"
    )
    def _compute_package_label_missing(self):
        for picking in self:
            picking.package_label_missing = bool(picking._get_packages_without_label())

    def _get_packages_without_label(self):
        self.ensure_one()
        return self.move_line_ids.result_package_id.filtered(
            lambda package: not package.carrier_tracking_ref
        ).sorted("name")

    def _package_label_ready(self):
        """Pickings whose labels are created per package by this module."""
        return self.filtered(
            lambda picking: picking.carrier_id.integration_level == "rate_and_ship"
            and picking.carrier_id.package_label_generation != "validate"
            and picking.picking_type_code == "outgoing"
        )

    def send_to_shipper(self):
        self.ensure_one()
        if not self._package_label_ready() or not self.move_line_ids.result_package_id:
            # goods without packages: one label for the delivery, as usual
            return super().send_to_shipper()
        if self.carrier_id.package_label_generation == "background":
            self.write({"package_label_queued": True, "package_label_error": False})
            self.env.ref("delivery_package_label.ir_cron_package_label")._trigger()
            self.message_post(
                body=self.env._(
                    "The carrier labels of %(count)s package(s) are being created "
                    "in background.",
                    count=len(self._get_packages_without_label()),
                )
            )
            return
        # on demand and when packed: validation creates the missing labels
        self._generate_package_labels(raise_error=True)

    def _generate_package_label(self, package):
        """Label of one package: tracking reference on the package, cost added
        to the delivery. Returns the label attachments."""
        self.ensure_one()
        result = self.carrier_id.send_package(self, package)
        package.carrier_tracking_ref = result["tracking_number"]
        price = self.carrier_id._apply_margins(
            result.get("exact_price") or 0.0, self.sale_id
        )
        self.carrier_price += price
        self.message_post(
            body=self.env._(
                "Package %(package)s: label %(ref)s created with %(carrier)s.",
                package=package.name,
                ref=result["tracking_number"],
                carrier=self.carrier_id.name,
            ),
            attachment_ids=result.get("attachment_ids", self.env["ir.attachment"]).ids,
        )
        return result.get("attachment_ids") or self.env["ir.attachment"]

    def _generate_package_labels(self, raise_error=False, commit=False):
        """Labels of every package without one. Each label survives the error of
        the next one, so a retry only creates the missing labels."""
        self.ensure_one()
        packages = self._get_packages_without_label()
        if not packages:
            raise UserError(
                self.env._(
                    "%(picking)s has no package without carrier label: put the goods "
                    "in packages first.",
                    picking=self.name,
                )
            )
        done = 0
        for package in packages:
            try:
                with self.env.cr.savepoint():
                    self._generate_package_label(package)
            except UserError as error:
                self.package_label_error = self.env._(
                    "Package %(package)s: %(error)s",
                    package=package.name,
                    error=error.args[0],
                )
                if raise_error and not done:
                    raise
                self.message_post(body=self.package_label_error)
                return False
            done += 1
            if commit:
                self.env["ir.cron"]._commit_progress(1)
        self.package_label_error = False
        self._package_labels_done()
        return True

    def _package_labels_done(self):
        self.package_label_queued = False
        self.message_post(
            body=Markup("%s<br/>%s")
            % (
                self.env._(
                    "Carrier labels of every package created with %(carrier)s.",
                    carrier=self.carrier_id.name,
                ),
                self.env._("Tracking references: %s", self.carrier_tracking_ref),
            )
        )
        self._add_delivery_cost_to_so()

    def action_generate_package_labels(self):
        for picking in self:
            if picking.state in ("draft", "cancel"):
                raise UserError(
                    self.env._(
                        "%s is not ready: carrier labels are created for deliveries "
                        "ready or done.",
                        picking.name,
                    )
                )
            picking._generate_package_labels()
        return True

    @api.model
    def _cron_generate_package_labels(self, limit=20):
        pickings = self.search([("package_label_queued", "=", True)], limit=limit)
        in_cron = bool(self.env.context.get("ir_cron_progress_id"))
        if in_cron:
            remaining = sum(len(p._get_packages_without_label()) for p in pickings)
            self.env["ir.cron"]._commit_progress(remaining=remaining)
        for picking in pickings:
            try:
                picking._generate_package_labels(commit=in_cron)
            except UserError as error:
                picking.write(
                    {
                        "package_label_queued": False,
                        "package_label_error": error.args[0],
                    }
                )
            if picking.package_label_error:
                # stop retrying the same error every run: the button retries it
                picking.package_label_queued = False
                picking.activity_schedule(
                    "mail.mail_activity_data_warning",
                    note=picking.package_label_error,
                    user_id=picking.user_id.id or self.env.uid,
                )
        return True

    def _package_label_print_action(self, package, attachments, package_action):
        """One file to print: the package label of the operation type (when it is
        printed on packing) followed by the carrier labels of the package."""
        if not attachments:
            return package_action
        documents = [base64.b64decode(attachment.datas) for attachment in attachments]
        is_pdf = all(document.startswith(b"%PDF") for document in documents)
        picking_type = self.picking_type_id
        # the package label goes first when it has the format of the carrier labels
        if picking_type.auto_print_package_label and is_pdf == (
            picking_type.package_label_to_print == "pdf"
        ):
            report = (
                "stock.action_report_package_barcode_small"
                if is_pdf
                else "stock.label_package_template"
            )
            documents.insert(
                0, self.env["ir.actions.report"]._render(report, package.ids)[0]
            )
        content = merge_pdf(documents) if is_pdf else b"\n".join(documents)
        name = f"Labels-{package.name}.{'pdf' if is_pdf else 'zpl'}"
        printout = self.env["ir.attachment"].create(
            {
                "name": name,
                "raw": content,
                "mimetype": "application/pdf" if is_pdf else "text/plain",
                "res_model": "stock.package",
                "res_id": package.id,
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{printout.id}?download=true",
            "target": "download",
        }
