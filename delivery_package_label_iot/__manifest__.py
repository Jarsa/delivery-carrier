# Copyright 2026 Jarsa
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
{
    "name": "Delivery Package Label IoT",
    "summary": "Print the carrier label of each package on the IoT box printer",
    "version": "19.0.1.0.0",
    "category": "Delivery",
    "website": "https://github.com/OCA/delivery-carrier",
    "author": "Jarsa, Odoo Community Association (OCA)",
    "license": "LGPL-3",
    "development_status": "Beta",
    "depends": ["delivery_package_label", "delivery_iot"],
    "data": ["report/stock_package_reports.xml"],
    "auto_install": True,
    "installable": True,
}
