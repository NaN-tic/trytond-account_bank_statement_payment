# The COPYRIGHT file at  the top level of this repository contains the full
# copyright notices and license terms.
import datetime
from sql.aggregate import Sum
from decimal import Decimal
from trytond.model import fields
from trytond.pool import Pool, PoolMeta

__metaclass__ = PoolMeta
__all__ = ['StatementLine', 'Group']

_ZERO = Decimal('0.0')


class StatementLine:
    __name__ = 'account.bank.statement.line'

    def _search_payments_reconciliation(self):
        pool = Pool()
        Group = pool.get('account.payment.group')
        MoveLine = pool.get('account.bank.statement.move.line')
        amount = self.company_amount - self.moves_amount
        search_amount = abs(amount)
        if search_amount == _ZERO:
            return

        kind = 'receivable' if amount > _ZERO else 'payable'
        domain = [
            ('journal.currency', '=', self.statement_currency),
            ('kind', '=', kind),
            ('total_amount', '=', search_amount),
            ]
        groups = []
        for group in Group.search(domain):
            append = True
            for payment in group.payments:
                if payment.line.reconciliation:
                    append = False
                    break
            if append:
                groups.append(group)

        for group in groups:
            for payment in group.payments:
                move_line = MoveLine()
                if payment.line:
                    line_amount = abs(payment.line.debit - payment.line.credit)
                    if line_amount == payment.amount:
                        line = payment.line
                        line.bank_statement_line_counterpart = self
                        line.save()
                        continue
                    move_line.account = payment.line.account
                else:
                    move_line.account = getattr(payment.party, 'account_%s' %
                        kind)
                move_line.party = payment.party
                move_line.amount = amount
                move_line.date = datetime.date(self.date.year, self.date.month,
                    self.date.day)
                move_line.line = self
                move_line.description = payment.description
                move_line.save()

    def _search_reconciliation(self):
        super(StatementLine, self)._search_reconciliation()
        self._search_payments_reconciliation()


class Group:
    __name__ = 'account.payment.group'

    total_amount = fields.Function(fields.Numeric('Total Amount'),
        'get_total_amount', searcher='search_total_amount')

    def get_total_amount(self, name=None):
        amount = Decimal('0.0')
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

        amount = Sum(Payment.amount.sql_column(payment))
        value = cls.total_amount.sql_format(value)

        query = payment.select(payment.group,
                group_by=(payment.group),
                having=Operator(amount, value)
                )
        return [('id', 'in', query)]
