# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from .account import *
from .statement import *
from .payment import *


def register():
    Pool.register(
        MoveLine,
        StatementLine,
        StatementMoveLine,
        Journal,
        Group,
        Payment,
        module='account_bank_statement_payment', type_='model')
