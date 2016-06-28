# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from decimal import Decimal
from sql.aggregate import Sum

from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, Bool

__all__ = ['Journal', 'Group', 'Payment']


class Journal:
    __name__ = 'account.payment.journal'
    __metaclass__ = PoolMeta
    clearing_percent = fields.Numeric('Bank Discount Percent',
        digits=(16, 4), domain=[
            ['OR',
                ('clearing_percent', '=', None),
                [
                    ('clearing_percent', '>', Decimal(0)),
                    ('clearing_percent', '<=', Decimal(1.0)),
                    ],
                ],
            ],
        states={
            'required': Bool(Eval('clearing_account')),
            }, depends=['clearing_account'],
        help='The percentage over the total owed amount that will be moved to '
        'Clearing Accoung when the payment is succeeded.')

    @fields.depends('clearing_account', 'clearing_percent')
    def on_change_with_clearing_percent(self):
        if self.clearing_account and not self.clearing_percent:
            return Decimal(1)
        return self.clearing_percent


class Group:
    __name__ = 'account.payment.group'
    __metaclass__ = PoolMeta

    total_amount = fields.Function(fields.Numeric('Total Amount'),
        'get_total_amount', searcher='search_total_amount')

    def get_total_amount(self, name=None):
        amount = Decimal(0)
        for payment in self.payments:
            amount += payment.amount
        return amount

    @classmethod
    def search_total_amount(cls, name, clause):
        pool = Pool()
        Payment = pool.get('account.payment')
        _, operator, value = clause
        Operator = fields.SQL_OPERATORS[operator]
        payment = Payment.__table__()
        value = Payment.amount._domain_value(operator, value)

        query = payment.select(payment.group,
                group_by=(payment.group),
                having=Operator(Sum(payment.amount), value)
                )
        return [('id', 'in', query)]


class Payment:
    __name__ = 'account.payment'
    __metaclass__ = PoolMeta

    def create_clearing_move(self, date=None):
        move = super(Payment, self).create_clearing_move(date=date)
        if move and self.journal.clearing_percent < Decimal(1):
            for line in move.lines:
                line.debit *= self.journal.clearing_percent
                line.credit *= self.journal.clearing_percent
        return move
