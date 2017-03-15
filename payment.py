# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from collections import defaultdict
from decimal import Decimal
from sql.aggregate import Sum

from trytond.model import ModelView, Workflow, fields
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
                    ('clearing_percent', '>', 0),
                    ('clearing_percent', '<=', 1),
                    ],
                ],
            ],
        states={
            'required': Bool(Eval('clearing_account')),
            'readonly': Eval('advance', False),
            }, depends=['clearing_account', 'advance'],
        help='The percentage over the total owed amount that will be moved to '
        'Clearing Accoung when the payment is succeeded.')
    advance = fields.Boolean('Advance',
        help='The Bank only advances the Due amount and it recover it at due '
        'date, indepently if the customer pays you.')

    @fields.depends('clearing_account', 'clearing_percent', 'advance')
    def on_change_with_clearing_percent(self):
        if self.advance:
            return Decimal(1)
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

    @classmethod
    @ModelView.button
    @Workflow.transition('succeeded')
    def succeed(cls, payments):
        pool = Pool()
        Line = pool.get('account.move.line')
        StatementMoveLine = pool.get('account.bank.statement.move.line')

        super(Payment, cls).succeed(payments)

        for payment in payments:
            if (payment.journal.clearing_account
                    and payment.journal.clearing_account.reconcile
                    and payment.clearing_move):
                statement_move_lines = StatementMoveLine.search([
                        ('payment', '=', payment),
                        ('account', '=', payment.journal.clearing_account),
                        ('line.state', '=', 'posted'),
                        ])
                if statement_move_lines:
                    to_reconcile = defaultdict(list)
                    lines = payment.clearing_move.lines
                    for sml in statement_move_lines:
                        lines += sml.move.lines
                    for line in lines:
                        if line.account.reconcile and not line.reconciliation:
                            key = (
                                line.account.id,
                                line.party.id if line.party else None)
                            to_reconcile[key].append(line)
                    for lines in to_reconcile.itervalues():
                        if not sum((l.debit - l.credit) for l in lines):
                            Line.reconcile(lines)

    def create_clearing_move(self, date=None):
        if self.journal.advance:
            # it doesn't create clearing because it's done when bank recover it
            return
        move = super(Payment, self).create_clearing_move(date=date)
        if move and self.journal.clearing_percent < Decimal(1):
            for line in move.lines:
                line.debit *= self.journal.clearing_percent
                line.debit = self.journal.currency.round(line.debit)
                line.credit *= self.journal.clearing_percent
                line.credit = self.journal.currency.round(line.credit)
        return move
