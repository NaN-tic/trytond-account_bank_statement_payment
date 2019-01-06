# The COPYRIGHT file at  the top level of this repository contains the full
# copyright notices and license terms.
import datetime
from collections import defaultdict
from decimal import Decimal

from trytond.model import ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.wizard import Wizard, StateTransition, StateView, Button
from trytond.pyson import Bool, Eval, If
from trytond.transaction import Transaction
from trytond.i18n import gettext
from trytond.exceptions import UserError
__all__ = ['StatementLine', 'StatementMoveLine', 'AddPaymentStart', 'AddPayment']

_ZERO = Decimal(0)


class StatementLine(metaclass=PoolMeta):
    __name__ = 'account.bank.statement.line'

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


class StatementMoveLine(metaclass=PoolMeta):
    __name__ = 'account.bank.statement.move.line'
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
        depends=['party', 'line_state', 'amount'])

    @classmethod
    def __setup__(cls):
        super(StatementMoveLine, cls).__setup__()
        if 'payment' not in cls.invoice.depends:
            for clause in cls.invoice.domain:
                if (isinstance(clause, If)
                        and clause._condition == Bool(Eval('account'))):
                    clause._condition = (Bool(Eval('account'))
                        & ~Bool(Eval('payment')))
            cls.invoice.depends.append('payment')

    @fields.depends('line')
    def on_change_with_line_state(self, name=None):
        pool = Pool()
        StatementLine = pool.get('account.bank.statement.line')
        return self.line.state if self.line else StatementLine.default_state()

    @fields.depends('party', 'payment', 'account',
        methods=['on_change_account'])
    def on_change_party(self):
        original_account = self.account
        super(StatementMoveLine, self).on_change_party()
        if self.payment:
            if self.payment.party != self.party:
                self.payment = None
            elif self.account != original_account:
                self.on_change_account()

    @fields.depends('account', 'payment')
    def on_change_account(self):
        super(StatementMoveLine, self).on_change_account()
        if self.payment:
            clearing_account = self.payment.journal.clearing_account
            if self.account != clearing_account:
                self.payment = None

    @fields.depends('payment')
    def on_change_invoice(self):
        pool = Pool()
        Payment = pool.get('account.payment')
        super(StatementMoveLine, self).on_change_invoice()
        if self.invoice and not self.payment:
            payments = Payment.search([
                    ('state', '=', 'processing'),
                    ('line.origin', '=', str(self.invoice)),
                    ])
            if payments:
                self.payment = payments[0]

    @fields.depends('payment', 'party', 'account', 'amount','line',
        '_parent_line._parent_statement.journal', '_parent_line.statement',
        methods=['on_change_invoice'])
    def on_change_payment(self):
        pool = Pool()
        Currency = pool.get('currency.currency')
        Invoice = pool.get('account.invoice')

        if self.payment:
            if not self.party:
                self.party = self.payment.party
            clearing_account = self.payment.journal.clearing_account
            if not self.account and clearing_account:
                # It's not the same that is done in account_payment_clearing
                if self.payment.journal.clearing_percent < Decimal(1):
                    if self.payment.clearing_move:
                        if isinstance(self.payment.line.origin, Invoice):
                            self.invoice = self.payment.line.origin
                            self.on_change_invoice()
                    else:
                        self.account = clearing_account
                else:
                    self.account = clearing_account
            if (not self.amount and self.line and self.line.journal):
                with Transaction().set_context(date=self.payment.date):
                    amount = Currency.compute(
                        self.payment.currency,
                        self.payment.amount,
                        self.line.journal.currency)
                if clearing_account and self.account == clearing_account:
                    if (self.payment.journal.clearing_percent < Decimal(1)
                            and self.payment.clearing_move):
                        amount *= (Decimal(1)
                            - self.payment.journal.clearing_percent)
                    else:
                        amount *= self.payment.journal.clearing_percent
                self.amount = self.line.journal.currency.round(amount)
                if self.payment.kind == 'payable':
                    self.amount *= -1

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
                    and not self.payment.journal.advance
                    and ((self.amount == -payment_amount)
                        or (advancement_amount
                            and self.amount == -advancement_amount))):
                Payment.fail([self.payment])
            elif (self.payment.state in ('processing', 'failed')
                    and ((self.account == self.payment.line.account
                            and self.amount == pending_amount)
                        or (self.payment.journal.advance
                            and self.account
                            != self.payment.journal.clearing_account
                            and self.amount == payment_amount))):
                Payment.succeed([self.payment])

            if (self.payment.clearing_move
                    and self.payment.clearing_move.state != 'posted'):
                Move.post([self.payment.clearing_move])

            to_reconcile = defaultdict(list)
            if not self.payment.line:
                raise UserError(gettext(
                    'account_bank_statement_payment.payment_without_account_move',
                    payment=self.payment.rec_name))
            lines = move.lines + (self.payment.line,)
            if self.payment.clearing_move:
                lines += self.payment.clearing_move.lines
            elif (self.payment.journal.clearing_account
                    and self.payment.journal.advance
                    and self.account == self.payment.journal.clearing_account):
                for statement_move_line in self.search([
                            ('payment', '=', self.payment),
                            ('account', '=', self.account),
                            ('line.state', '=', 'posted'),
                            ]):
                    lines += statement_move_line.move.lines

            for line in lines:
                if line.account.reconcile and not line.reconciliation:
                    key = (
                        line.account.id,
                        line.party.id if line.party else None)
                    to_reconcile[key].append(line)
            for lines in list(to_reconcile.values()):
                if not sum((l.debit - l.credit) for l in lines):
                    MoveLine.reconcile(lines)
        return move

    def _check_invoice_amount_to_pay(self):
        if self.payment:
            return
        super(StatementMoveLine, self)._check_invoice_amount_to_pay()

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


class AddPaymentStart(ModelView):
    'Add Payment Start'
    __name__ = 'account.bank.statement.payment.add.start'
    payments = fields.Many2Many('account.payment', None, None, 'Payments')


class AddPayment(Wizard):
    'Add Payment'
    __name__ = 'account.bank.statement.payment.add'
    start = StateView('account.bank.statement.payment.add.start',
        'account_bank_statement_payment.account_bank_statement_payment_add_start', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Add', 'add', 'tryton-ok', default=True),
            ])
    add = StateTransition()

    def transition_add(self):
        pool = Pool()
        StatementLine = pool.get('account.bank.statement.line')
        BSMoveLine = pool.get('account.bank.statement.move.line')

        payments = self.start.payments

        to_create = []
        for line in StatementLine.browse(Transaction().context['active_ids']):
            for payment in payments:
                # TODO move get account to new method
                if payment.journal.clearing_account:
                    account = payment.journal.clearing_account
                elif payment.line and payment.line.account:
                    account = payment.line.account
                elif payment.kind == 'payable':
                    if not payment.party.account_payable:
                        continue
                    account = payment.party.account_payable
                elif payment.kind == 'receivable':
                    if not payment.party.account_receivable:
                        continue
                    account = payment.party.account_receivable

                bsmove_line = BSMoveLine()
                bsmove_line.line = line
                bsmove_line.payment = payment
                bsmove_line.invoice = None
                changes = bsmove_line.on_change_payment()
                bsmove_line.date = line.date.date()
                bsmove_line.amount = changes.get('amount') or payment.amount
                bsmove_line.party = changes.get('party') or payment.party
                bsmove_line.account = changes.get('account') or account
                bsmove_line.invoice = changes.get('invoice')
                bsmove_line.description = payment.description
                # bsmove_line.move =
                to_create.append(bsmove_line._save_values)

        if to_create:
            BSMoveLine.create(to_create)

        return 'end'
