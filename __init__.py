# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from . import account
from . import statement
from . import payment


def register():
    Pool.register(
        account.MoveLine,
        payment.Journal,
        payment.Group,
        payment.Payment,
        statement.AddPaymentStart,
        statement.Group,
        statement.StatementLine,
        statement.StatementMoveLine,
        module='account_bank_statement_payment', type_='model')
    Pool.register(
        statement.AddPayment,
        module='account_bank_statement_payment', type_='wizard')
