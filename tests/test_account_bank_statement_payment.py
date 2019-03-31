# This file is part of the account_bank_statement_payment module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from decimal import Decimal
import datetime
import doctest
import unittest
from trytond.pool import Pool
import trytond.tests.test_tryton
from trytond.tests.test_tryton import ModuleTestCase, with_transaction
from trytond.tests.test_tryton import doctest_teardown
from trytond.tests.test_tryton import doctest_checker

from trytond.modules.company.tests import create_company, set_company
from trytond.modules.account.tests import create_chart, get_fiscalyear
from trytond.modules.account_invoice.tests import set_invoice_sequences


class AccountBankStatementPaymentTestCase(ModuleTestCase):
    'Test Account Bank Statement Payment module'
    module = 'account_bank_statement_payment'

    @with_transaction()
    def test_bank_reconciliation(self):
        'Test bank reconciliation'
        pool = Pool()
        Date = pool.get('ir.date')
        FiscalYear = pool.get('account.fiscalyear')
        Journal = pool.get('account.journal')
        Account = pool.get('account.account')
        Party = pool.get('party.party')
        Move = pool.get('account.move')
        Line = pool.get('account.move.line')
        PaymentJournal = pool.get('account.payment.journal')
        Payment = pool.get('account.payment')
        Group = pool.get('account.payment.group')
        StatementJournal = pool.get('account.bank.statement.journal')
        Statement = pool.get('account.bank.statement')
        StatementLine = pool.get('account.bank.statement.line')

        company = create_company()
        with set_company(company):
            create_chart(company)
            fiscalyear = set_invoice_sequences(get_fiscalyear(company))
            fiscalyear.save()
            FiscalYear.create_period([fiscalyear])
            period = fiscalyear.periods[0]
            payment_journal, = PaymentJournal.create([{
                        'name': 'Manual',
                        'process_method': 'manual',
                        }])
            journal_revenue, = Journal.search([
                    ('code', '=', 'REV'),
                    ])
            revenue, = Account.search([
                    ('type.revenue', '=',True),
                    ])
            receivable, = Account.search([
                    ('type.receivable', '=', True),
                    ])
            expense, = Account.search([
                    ('type.expense', '=', True),
                    ])
            payable, = Account.search([
                    ('type.payable', '=', True),
                    ])
            cash, = Account.search([
                    ('name', '=', 'Main Cash'),
                    ])
            cash.bank_reconcile = True
            cash.save()
            #Create some parties
            customer1, customer2, supplier1, supplier2 = Party.create([{
                            'name': 'customer1',
                            'account_receivable': receivable,
                            'account_payable': payable,
                        }, {
                            'name': 'customer2',
                            'account_receivable': receivable,
                            'account_payable': payable,
                        }, {
                            'name': 'supplier1',
                            'account_receivable': receivable,
                            'account_payable': payable,
                        }, {
                            'name': 'supplier2',
                            'account_receivable': receivable,
                            'account_payable': payable,
                        }])
            # Create some moves
            vlist = [
                {
                    'period': period.id,
                    'journal': journal_revenue.id,
                    'date': period.start_date,
                    'lines': [
                        ('create', [{
                                    'account': revenue.id,
                                    'credit': Decimal('100.0'),
                                    }, {
                                    'party': customer1.id,
                                    'account': receivable.id,
                                    'debit': Decimal('100.0'),
                                    }]),
                        ],
                    },
                ]
            moves = Move.create(vlist)
            Move.post(moves)

            line, = Line.search([
                    ('account', '=', receivable)
                    ])
            payments = Payment.create([
                    {
                        'journal': payment_journal.id,
                        'party': line.party.id,
                        'kind': 'receivable',
                        'amount': line.payment_amount,
                        'line': line,
                        'date': Date.today(),
                        },
                    {
                        'journal': payment_journal.id,
                        'party': line.party.id,
                        'kind': 'receivable',
                        'amount': Decimal('10.0'),
                        'date': Date.today(),
                        },
                    ])

            self.assertEqual(sum([p.amount for p in payments]),
                Decimal('110.0'))
            Payment.approve(payments)
            group, = Group.create([{
                        'kind': 'receivable',
                        'journal': payment_journal.id,
                        }])
            Payment.process(payments, lambda: group)

            self.assertEqual(all([p.state == 'processing' for p in payments]),
                    True)

            cash_journal, = Journal.copy([journal_revenue], {
                        'type': 'cash',
                    })

            statement_journal, = StatementJournal.create([{
                        'name': 'Bank',
                        'journal': cash_journal.id,
                        'account': cash.id,
                        }])
            statement, = Statement.create([{
                        'journal': statement_journal.id,
                        'date': datetime.datetime.now(),
                        'lines': [
                            ('create', [{
                                        'date': datetime.datetime.now(),
                                        'description': 'desc',
                                        'amount': Decimal('110.0'),
                                        }]),
                            ],
                        }])
            Statement.confirm([statement])
            statement_line, = statement.lines
            self.assertEqual(statement_line.company_amount, Decimal('110.0'))
            self.assertEqual(statement_line.moves_amount, Decimal('0.0'))
            StatementLine.search_reconcile([statement_line])
            self.assertEqual(statement_line.moves_amount, Decimal('110.0'))
            self.assertEqual(list(statement_line.counterpart_lines), [line])
            self.assertEqual(len(statement_line.lines), 1)


def suite():
    suite = trytond.tests.test_tryton.suite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
        AccountBankStatementPaymentTestCase))
    suite.addTests(doctest.DocFileSuite(
            'scenario_bank_statement_payment_bank_discount.rst',
            tearDown=doctest_teardown, encoding='utf-8',
            checker=doctest_checker,
            optionflags=doctest.REPORT_ONLY_FIRST_FAILURE))
    return suite
