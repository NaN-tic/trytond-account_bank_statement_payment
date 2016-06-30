# The COPYRIGHT file at  the top level of this repository contains the full
# copyright notices and license terms.
import datetime
from collections import defaultdict
from decimal import Decimal
from sql.aggregate import Sum

from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Bool, Eval, If
from trytond.transaction import Transaction

__all__ = ['StatementLine', 'StatementMoveLine', 'Group']

_ZERO = Decimal(0)


class StatementLine:
    __metaclass__ = PoolMeta
    __name__ = 'account.bank.statement.line'
    __metaclass__ = PoolMeta

    def _search_payments(self, amount):
        """
        Return a list of payments from payment group with total equal to amount
        """
        pool = Pool()
        Group = pool.get('account.payment.group')

        search_amount = abs(amount)
        if search_amount == _ZERO:
            return []

        kind = 'receivable' if amount > _ZERO else 'payable'
        domain = [
            ('journal.currency', '=', self.statement_currency),
            ('kind', '=', kind),
            ('total_amount', '=', search_amount),
            ]
        payments = []
        for group in Group.search(domain):
            found = True
            for payment in group.payments:
                if payment.line and payment.line.reconciliation:
                    found = False
                    break
            if found:
                payments = group.payments
                break
        return payments

    def _search_payments_reconciliation(self):
        pool = Pool()
        MoveLine = pool.get('account.bank.statement.move.line')

        amount = self.company_amount - self.moves_amount
        kind = 'receivable' if amount > _ZERO else 'payable'
        payments = self._search_payments(amount)

        for payment in payments:
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
            move_line.amount = payment.amount
            move_line.date = datetime.date(self.date.year, self.date.month,
                self.date.day)
            move_line.line = self
            move_line.description = payment.description
            move_line.save()

    def _search_reconciliation(self):
        super(StatementLine, self)._search_reconciliation()
        self._search_payments_reconciliation()


class StatementMoveLine:
    __name__ = 'account.bank.statement.move.line'
    __metaclass__ = PoolMeta
    line_state = fields.Function(fields.Selection([
                ('draft', 'Draft'),
                ('confirmed', 'Confirmed'),
                ('canceled', 'Canceled'),
                ('posted', 'Posted'),
                ], 'State'),
        'on_change_with_line_state')
    payment = fields.Many2One('account.payment', 'Payment',
        domain=[
            If(Bool(Eval('party')), [('party', '=', Eval('party'))], []),
            If(Eval('line_state').in_(['canceled', 'posted']),
                ('state', 'in', ['processing', 'succeeded', 'failed']),
                If(Eval('amount', 0.0) < 0.0,
                    ('state', 'in', ['processing', 'succeeded']),
                    ('state', 'in', ['processing', 'failed']))),
            ],
        depends=['party'])

    @classmethod
    def __setup__(cls):
        super(StatementMoveLine, cls).__setup__()
        for clause in cls.invoice.domain:
            if (isinstance(clause, If)
                    and clause._condition == Bool(Eval('account'))):
                clause._condition = (Bool(Eval('account'))
                    & ~Bool(Eval('payment')))

    @fields.depends('line')
    def on_change_with_line_state(self, name=None):
        pool = Pool()
        StatementLine = pool.get('account.bank.statement.line')
        return self.line.state if self.line else StatementLine.default_state()

    @fields.depends('party', 'payment', methods=['account'])
    def on_change_party(self):
        changes = super(StatementMoveLine, self).on_change_party()
        if self.payment:
            if self.payment.party != self.party:
                changes['payment'] = None
                self.payment = None
            elif changes.get('account'):
                changes.update(self.on_change_account())
        return changes

    @fields.depends('account', 'payment')
    def on_change_account(self):
        changes = super(StatementMoveLine, self).on_change_account()
        if self.payment:
            clearing_account = self.payment.journal.clearing_account
            if self.account != clearing_account:
                changes['payment'] = None
                self.payment = None
        return changes

    @fields.depends('payment')
    def on_change_invoice(self):
        pool = Pool()
        Payment = pool.get('account.payment')
        changes = super(StatementMoveLine, self).on_change_invoice()
        if self.invoice and not self.payment:
            payments = Payment.search([
                    ('state', '=', 'processing'),
                    ('line.origin', '=', str(self.invoice)),
                    ])
            if payments:
                changes['payment'] = payments[0].id
                changes['payment.rec_name'] = payments[0].rec_name
                self.payment = payments[0]
        return changes

    @fields.depends('payment', 'party', 'account', 'amount',
        '_parent_line._parent_statement.journal',
        methods=['invoice'])
    def on_change_payment(self):
        pool = Pool()
        Currency = pool.get('currency.currency')
        Invoice = pool.get('account.invoice')
        changes = {}
        if self.payment:
            if not self.party:
                changes['party'] = self.payment.party.id
                changes['party.rec_name'] = self.payment.party.rec_name
                self.party = self.payment.party
            clearing_account = self.payment.journal.clearing_account
            if not self.account and clearing_account:
                # It's not the same that is done in account_payment_clearing
                if self.payment.journal.clearing_percent < Decimal(1):
                    if self.payment.clearing_move:
                        if isinstance(self.payment.line.origin, Invoice):
                            changes['invoice'] = self.payment.line.origin.id
                            self.invoice = self.payment.line.origin
                            changes.update(self.on_change_invoice())
                    else:
                        changes['account'] = clearing_account.id
                        changes['account.rec_name'] = clearing_account.rec_name
                        self.account = clearing_account
                else:
                    changes['account'] = clearing_account.id
                    changes['account.rec_name'] = clearing_account.rec_name
                    self.account = clearing_account
            if (not self.amount and self.line.statement
                    and self.line.statement.journal):
                with Transaction().set_context(date=self.payment.date):
                    amount = Currency.compute(
                        self.payment.currency,
                        self.payment.amount,
                        self.line.statement.journal.currency)
                if clearing_account and self.account == clearing_account:
                    if (self.payment.journal.clearing_percent < Decimal(1)
                            and self.payment.clearing_move):
                        amount *= (Decimal(1)
                            - self.payment.journal.clearing_percent)
                    else:
                        amount *= self.payment.journal.clearing_percent
                changes['amount'] = amount
                self.amount = amount
                if self.payment.kind == 'payable':
                    changes['amount'] *= -1
                    self.amount *= -1
        return changes

    def create_move(self):
        pool = Pool()
        Currency = pool.get('currency.currency')
        Move = pool.get('account.move')
        MoveLine = pool.get('account.move.line')
        Payment = pool.get('account.payment')

        move = super(StatementMoveLine, self).create_move()

        if self.payment:
            payment_amount = Currency.compute(self.payment.currency,
                self.payment.amount, self.line.statement.journal.currency)
            if self.payment.kind == 'payable':
                payment_amount *= -1

            if (self.payment.journal.clearing_account
                    and self.payment.journal.clearing_percent < Decimal(1)):
                advancement_amount = (payment_amount
                    * self.payment.journal.clearing_percent)
                pending_amount = (payment_amount
                    * (Decimal(1) - self.payment.journal.clearing_percent))
            else:
                advancement_amount = pending_amount = None

            if (self.payment.state in ('processing', 'succeeded')
                    and ((self.amount == -payment_amount)
                        or (advancement_amount
                            and self.amount == -advancement_amount))):
                Payment.fail([self.payment])
            elif (self.payment.state in ('processing', 'failed')
                    and self.account == self.payment.line.account
                    and self.amount == pending_amount):
                Payment.succeed([self.payment])

            if (self.payment.clearing_move
                    and self.payment.clearing_move.state != 'posted'):
                Move.post([self.payment.clearing_move])

            to_reconcile = defaultdict(list)
            lines = move.lines + (self.payment.line,)
            if self.payment.clearing_move:
                lines += self.payment.clearing_move.lines
            for line in lines:
                if line.account.reconcile and not line.reconciliation:
                    key = (
                        line.account.id,
                        line.party.id if line.party else None)
                    to_reconcile[key].append(line)
            for lines in to_reconcile.itervalues():
                if not sum((l.debit - l.credit) for l in lines):
                    MoveLine.reconcile(lines)
        return move

    def _get_move(self):
        move = super(StatementMoveLine, self)._get_move()
        if move and self.payment:
            move.origin = self.payment
        return move

    @classmethod
    def copy(cls, lines, default=None):
        if default is None:
            default = {}
        else:
            default = default.copy()
        default.setdefault('payment', None)
        return super(StatementMoveLine, cls).copy(lines, default=default)


class Group:
    __name__ = 'account.payment.group'
    __metaclass__ = PoolMeta
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
        value = Payment.amount._domain_value(operator, value)

        query = payment.select(payment.group,
                group_by=(payment.group),
                having=Operator(Sum(payment.amount), value)
                )
        return [('id', 'in', query)]
