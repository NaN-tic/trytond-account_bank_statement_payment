#!/usr/bin/env python
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import sys
import os
import optparse
DIR = os.path.abspath(os.path.normpath(os.path.join(__file__,
    '..', '..', '..', '..', '..', 'trytond')))
if os.path.isdir(DIR):
    sys.path.insert(0, os.path.dirname(DIR))

from decimal import Decimal
import datetime
import unittest
import trytond.tests.test_tryton
from trytond.tests.test_tryton import test_depends
from trytond.tests.test_tryton import POOL, DB_NAME, USER, CONTEXT
from trytond.transaction import Transaction


class TestCase(unittest.TestCase):
    '''
    Test module.
    '''

    def setUp(self):
        trytond.tests.test_tryton.install_module(
            'account_bank_statement_payment')
        self.account = POOL.get('account.account')
        self.company = POOL.get('company.company')
        self.user = POOL.get('res.user')
        self.date = POOL.get('ir.date')
        self.party = POOL.get('party.party')
        self.party_address = POOL.get('party.address')
        self.fiscalyear = POOL.get('account.fiscalyear')
        self.move = POOL.get('account.move')
        self.line = POOL.get('account.move.line')
        self.journal = POOL.get('account.journal')
        self.payment_journal = POOL.get('account.payment.journal')
        self.statement_journal = POOL.get('account.bank.statement.journal')
        self.payment = POOL.get('account.payment')
        self.group = POOL.get('account.payment.group')
        self.period = POOL.get('account.period')
        self.pay_line = POOL.get('account.move.line.pay', type='wizard')
        self.statement = POOL.get('account.bank.statement')
        self.statement_line = POOL.get('account.bank.statement.line')

    def test0006depends(self):
        'Test depends'
        test_depends()

    def test0010_bank_reconciliation(self):
        'Test bank reconciliation'
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            fiscalyear, = self.fiscalyear.search([])
            period = fiscalyear.periods[0]
            payment_journal, = self.payment_journal.create([{
                        'name': 'Manual',
                        'process_method': 'manual',
                        }])
            journal_revenue, = self.journal.search([
                    ('code', '=', 'REV'),
                    ])
            revenue, = self.account.search([
                    ('kind', '=', 'revenue'),
                    ])
            receivable, = self.account.search([
                    ('kind', '=', 'receivable'),
                    ])
            expense, = self.account.search([
                    ('kind', '=', 'expense'),
                    ])
            payable, = self.account.search([
                    ('kind', '=', 'payable'),
                    ])
            cash, = self.account.search([
                    ('kind', '=', 'other'),
                    ('name', '=', 'Main Cash'),
                    ])
            cash.bank_reconcile = True
            cash.save()
            #Create some parties
            customer1, customer2, supplier1, supplier2 = self.party.create([{
                            'name': 'customer1',
                        }, {
                            'name': 'customer2',
                        }, {
                            'name': 'supplier1',
                        }, {
                            'name': 'supplier2',
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
            moves = self.move.create(vlist)
            self.move.post(moves)

            line, = self.line.search([
                    ('account', '=', receivable)
                    ])
            payments = self.payment.create([
                    {
                        'journal': payment_journal.id,
                        'party': line.party.id,
                        'kind': 'receivable',
                        'amount': line.payment_amount,
                        'line': line,
                        'date': self.date.today(),
                        },
                    {
                        'journal': payment_journal.id,
                        'party': line.party.id,
                        'kind': 'receivable',
                        'amount': Decimal('10.0'),
                        'date': self.date.today(),
                        },
                    ])

            self.assertEqual(sum([p.amount for p in payments]),
                Decimal('110.0'))
            self.payment.approve(payments)
            group, = self.group.create([{
                        'kind': 'receivable',
                        'journal': payment_journal.id,
                        }])
            self.payment.process(payments, lambda: group)

            self.assertEqual(all([p.state == 'processing' for p in payments]),
                    True)

            cash_journal, = self.journal.copy([journal_revenue], {
                        'type': 'cash',
                        'credit_account': cash.id,
                        'debit_account': cash.id,
                    })

            statement_journal, = self.statement_journal.create([{
                        'name': 'Bank',
                        'journal': cash_journal.id,
                        }])
            statement, = self.statement.create([{
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
            self.statement.confirm([statement])
            statement_line, = statement.lines
            self.assertEqual(statement_line.company_amount, Decimal('110.0'))
            self.assertEqual(statement_line.moves_amount, Decimal('0.0'))
            self.statement_line.search_reconcile([statement_line])
            self.assertEqual(statement_line.moves_amount, Decimal('110.0'))
            self.assertEqual(statement_line.counterpart_lines, [line])
            self.assertEqual(len(statement_line.lines), 1)


def suite():
    suite = trytond.tests.test_tryton.suite()
    from trytond.modules.account.tests import test_account
    for test in test_account.suite():
        #Skip doctest
        class_name = test.__class__.__name__
        if test not in suite and class_name != 'DocFileCase':
            suite.addTest(test)
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestCase))
    return suite

if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
