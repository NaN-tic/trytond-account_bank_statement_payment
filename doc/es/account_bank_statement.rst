#:before:account_bank_statement_counterpart/account_bank_statement:paragraph:remesas#

Si el sistema no encuentra ningún efecto cuyo importe coincida, buscará
entonces remesas del mismo importe que la línea de movimientos. Si encuentra
alguna remesa, el sistema añadirá:

* Un efecto para cada línea de la remesa que esté totalmente pagado (el
  importe del pago sea el mismo que el importe de la línea de remesa).

* Una transacción para cada línea de remesa que se corresponda con el pago
  parcial de un efecto. Se utilizará como importe de la transacción el
  importe del pago y como cuenta la misma cuenta del efecto.

* Una transacción para cada línea de remesa que no se corresponda con un
  efecto, utilizando la cuenta a cobrar/pagar del tercero como cuenta y el
  importe del pago como importe.
    
