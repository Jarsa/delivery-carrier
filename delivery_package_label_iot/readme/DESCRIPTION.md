Print the carrier labels that `delivery_package_label` creates per package on
the printer of the IoT box (`delivery_iot`, Odoo Enterprise), without
downloading them:

- **When each package is packed**: *Put in Pack* sends the file of the package
  (the package label of the operation type when it prints on packing, followed
  by the carrier label) to the printer of the report *Package Carrier Labels*.
- **On demand**: *Create Carrier Labels* sends the labels of the delivery to the
  printer of the report *Shipping Labels* when the operation type has *Auto
  Print Carrier Labels*.

Labels created on validation or in background are printed by `delivery_iot` as
usual (*Auto Print Carrier Labels* on the operation type, or *Print* on the
delivery). ZPL and PDF labels are both supported: the IoT box sends ZPL as is
to label printers.
