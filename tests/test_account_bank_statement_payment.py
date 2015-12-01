# This file is part of the account_bank_statement_payment module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import unittest
import trytond.tests.test_tryton
from trytond.tests.test_tryton import ModuleTestCase


class AccountBankStatementPaymentTestCase(ModuleTestCase):
    'Test Account Bank Statement Payment module'
    module = 'account_bank_statement_payment'


def suite():
    suite = trytond.tests.test_tryton.suite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
        AccountBankStatementPaymentTestCase))
    return suite