1. Go to *Inventory > Configuration > Delivery Methods* and open a method whose
   integration creates labels per package, with *Integration Level* *Get Rate
   and Create Shipment*.
2. Choose *Carrier Labels*.
3. For *When each package is packed*, on the operation type (tab *Barcode App*
   or *Hardware*) enable *Print Package Label* and choose the same format as
   the carrier labels (ZPL or PDF) to get both labels in one file.

The *Tracking Reference per Package* of the delivery method is not required for
the modes other than *On validation*: the labels fill it in.

Carrier integrations support this module by implementing
`<delivery_type>_send_package(picking, package)`, which creates the label of
one package and returns `tracking_number`, `exact_price` and `attachment_ids`.
