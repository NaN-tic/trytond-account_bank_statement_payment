# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from statement import *


def register():
    Pool.register(
        StatementLine,
        Group,
        module='account_bank_statement_payment', type_='model')
