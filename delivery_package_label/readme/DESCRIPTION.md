Choose, per delivery method, when the carrier labels of a delivery are created
when the carrier integration creates one label per package:

- **On validation**: the standard flow of Odoo.
- **On demand**: a *Create Carrier Labels* button on the delivery, once it is
  ready, creates the label of each package; validation creates the missing ones.
- **In background**: validation is immediate and a scheduled action creates the
  labels one package at a time, saving each one. For deliveries with dozens of
  packages, where creating every label while validating would exceed the time
  limit of the request.
- **When each package is packed**: *Put in Pack* creates the label of the new
  package and downloads one file with the package label of the operation type
  (when it prints on packing) followed by the carrier label, ready for the
  label printer.

Each label is saved on its package (tracking reference of
`delivery_package_tracking`) as soon as the carrier returns it: an error on one
package keeps the labels already created, and the button or the next run only
creates the missing ones.
