# Copyright 2026 Jarsa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
{
    "name": "Delivery Package Label",
    "summary": "Carrier label per package: on validation, on demand, in background "
    "or when the package is packed",
    "version": "19.0.1.0.0",
    "category": "Delivery",
    "website": "https://github.com/OCA/delivery-carrier",
    "author": "Jarsa, Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "development_status": "Beta",
    "depends": ["delivery_package_tracking"],
    "data": [
        "data/ir_cron_data.xml",
        "views/delivery_carrier_views.xml",
        "views/stock_picking_views.xml",
    ],
    "installable": True,
}
