=======================================
Account Bank Statement Payment Scenario
=======================================

Imports::

    >>> import datetime
    >>> from dateutil.relativedelta import relativedelta
    >>> from decimal import Decimal
    >>> from operator import attrgetter
    >>> from proteus import config, Model, Wizard
    >>> today = datetime.date.today()
    >>> now = datetime.datetime.now()

Create database::

    >>> config = config.set_trytond()
    >>> config.pool.test = True

Install account_bank_statement_payment::

    >>> Module = Model.get('ir.module.module')
    >>> account_bank_module, = Module.find(
    ...     [('name', '=', 'account_bank_statement_payment')])
    >>> Module.install([account_bank_module.id], config.context)
    >>> Wizard('ir.module.module.install_upgrade').execute('upgrade')

Create company::

    >>> Currency = Model.get('currency.currency')
    >>> CurrencyRate = Model.get('currency.currency.rate')
    >>> currencies = Currency.find([('code', '=', 'USD')])
    >>> if not currencies:
    ...     currency = Currency(name='US Dollar', symbol=u'$', code='USD',
    ...         rounding=Decimal('0.01'), mon_grouping='[]',
    ...         mon_decimal_point='.')
    ...     currency.save()
    ...     CurrencyRate(date=today + relativedelta(month=1, day=1),
    ...         rate=Decimal('1.0'), currency=currency).save()
    ... else:
    ...     currency, = currencies
    >>> Company = Model.get('company.company')
    >>> Party = Model.get('party.party')
    >>> company_config = Wizard('company.company.config')
    >>> company_config.execute('company')
    >>> company = company_config.form
    >>> party = Party(name='Dunder Mifflin')
    >>> party.save()
    >>> company.party = party
    >>> company.currency = currency
    >>> company_config.execute('add')
    >>> company, = Company.find([])

Reload the context::

    >>> User = Model.get('res.user')
    >>> config._context = User.get_preferences(True, config.context)

Create fiscal year::

    >>> FiscalYear = Model.get('account.fiscalyear')
    >>> Sequence = Model.get('ir.sequence')
    >>> SequenceStrict = Model.get('ir.sequence.strict')
    >>> fiscalyear = FiscalYear(name=str(today.year))
    >>> fiscalyear.start_date = today + relativedelta(month=1, day=1)
    >>> fiscalyear.end_date = today + relativedelta(month=12, day=31)
    >>> fiscalyear.company = company
    >>> post_move_seq = Sequence(name=str(today.year), code='account.move',
    ...     company=company)
    >>> post_move_seq.save()
    >>> fiscalyear.post_move_sequence = post_move_seq
    >>> invoice_seq = SequenceStrict(name=str(today.year),
    ...     code='account.invoice', company=company)
    >>> invoice_seq.save()
    >>> fiscalyear.out_invoice_sequence = invoice_seq
    >>> fiscalyear.in_invoice_sequence = invoice_seq
    >>> fiscalyear.out_credit_note_sequence = invoice_seq
    >>> fiscalyear.in_credit_note_sequence = invoice_seq
    >>> fiscalyear.save()
    >>> FiscalYear.create_period([fiscalyear.id], config.context)

Create chart of accounts::

    >>> AccountTemplate = Model.get('account.account.template')
    >>> Account = Model.get('account.account')
    >>> account_template, = AccountTemplate.find([('parent', '=', None)])
    >>> create_chart = Wizard('account.create_chart')
    >>> create_chart.execute('account')
    >>> create_chart.form.account_template = account_template
    >>> create_chart.form.company = company
    >>> create_chart.execute('create_account')
    >>> receivable, = Account.find([
    ...         ('kind', '=', 'receivable'),
    ...         ('company', '=', company.id),
    ...         ])
    >>> payable, = Account.find([
    ...         ('kind', '=', 'payable'),
    ...         ('company', '=', company.id),
    ...         ])
    >>> revenue, = Account.find([
    ...         ('kind', '=', 'revenue'),
    ...         ('company', '=', company.id),
    ...         ])
    >>> expense, = Account.find([
    ...         ('kind', '=', 'expense'),
    ...         ('company', '=', company.id),
    ...         ])
    >>> account_tax, = Account.find([
    ...         ('kind', '=', 'other'),
    ...         ('company', '=', company.id),
    ...         ('name', '=', 'Main Tax'),
    ...         ])
    >>> cash, = Account.find([
    ...         ('kind', '=', 'other'),
    ...         ('company', '=', company.id),
    ...         ('name', '=', 'Main Cash'),
    ...         ])
    >>> cash.bank_reconcile = True
    >>> cash.reconcile = True
    >>> cash.save()
    >>> customer_bank_discounts = Account(
    ...     name='Customers Bank Discount',
    ...     type=receivable.type,
    ...     bank_reconcile=True,
    ...     reconcile=True,
    ...     party_required=True,
    ...     deferral=True,
    ...     parent=receivable.parent,
    ...     kind='other')
    >>> customer_bank_discounts.save()
    >>> create_chart.form.account_receivable = receivable
    >>> create_chart.form.account_payable = payable
    >>> create_chart.execute('create_properties')

Create and get journals::

    >>> sequence = Sequence(name='Bank', code='account.journal',
    ...     company=company)
    >>> sequence.save()
    >>> AccountJournal = Model.get('account.journal')
    >>> bank_journal = AccountJournal(
    ...     name='Bank Statement',
    ...     type='cash',
    ...     credit_account=cash,
    ...     debit_account=cash,
    ...     sequence=sequence)
    >>> bank_journal.save()
    >>> revenue_journal, = AccountJournal.find([('code', '=', 'REV')])

Create payment journal::

    >>> PaymentJournal = Model.get('account.payment.journal')
    >>> payment_receivable_100_journal = PaymentJournal(
    ...     name='Manual receivable 100% discount',
    ...     process_method='manual',
    ...     clearing_journal=revenue_journal,
    ...     clearing_account=customer_bank_discounts)
    >>> payment_receivable_100_journal.save()
    >>> payment_receivable_100_journal.clearing_percent
    Decimal('1')
    >>> payment_receivable_80_journal = PaymentJournal(
    ...     name='Manual receivable 80% discount',
    ...     process_method='manual',
    ...     clearing_journal=revenue_journal,
    ...     clearing_account=customer_bank_discounts,
    ...     clearing_percent=Decimal('0.8'))
    >>> payment_receivable_80_journal.save()

Create statement journal::

    >>> StatementJournal = Model.get('account.bank.statement.journal')
    >>> statement_journal = StatementJournal(
    ...     name='Test',
    ...     journal=bank_journal)
    >>> statement_journal.save()

Create party::

    >>> Party = Model.get('party.party')
    >>> supplier = Party(name='Supplier')
    >>> supplier.save()
    >>> customer = Party(name='Customer')
    >>> customer.save()

Create payment term::

    >>> PaymentTerm = Model.get('account.invoice.payment_term')
    >>> payment_term = PaymentTerm(name='Direct')
    >>> payment_term_line = payment_term.lines.new()
    >>> payment_term_line.type = 'remainder'
    >>> payment_term_line.days = 0
    >>> payment_term.save()

Create customer invoice::

    >>> Invoice = Model.get('account.invoice')
    >>> customer_invoice = Invoice(type='out_invoice')
    >>> customer_invoice.party = customer
    >>> customer_invoice.payment_term = payment_term
    >>> invoice_line = customer_invoice.lines.new()
    >>> invoice_line.quantity = 1
    >>> invoice_line.unit_price = Decimal('100')
    >>> invoice_line.account = revenue
    >>> invoice_line.description = 'Test'
    >>> customer_invoice.save()
    >>> customer_invoice.click('post')
    >>> customer_invoice.state
    u'posted'

Create customer invoice payment::

    >>> Payment = Model.get('account.payment')
    >>> line, = [l for l in customer_invoice.move.lines
    ...     if l.account == receivable]
    >>> pay_line = Wizard('account.move.line.pay', [line])
    >>> pay_line.form.journal = payment_receivable_100_journal
    >>> pay_line.execute('pay')
    >>> payment, = Payment.find([('state', '=', 'draft')])
    >>> payment.amount
    Decimal('100.00')
    >>> payment.click('approve')
    >>> payment.state
    u'approved'
    >>> process_payment = Wizard('account.payment.process', [payment])
    >>> process_payment.execute('process')
    >>> payment.reload()
    >>> payment.state
    u'processing'

Check invoice is still pending to pay so the amount is in customer's debit account::

    >>> customer_invoice.reload()
    >>> customer_invoice.state
    u'posted'
    >>> receivable.reload()
    >>> receivable.balance
    Decimal('100.00')

Create and confirm bank statement::

    >>> BankStatement = Model.get('account.bank.statement')
    >>> statement = BankStatement(journal=statement_journal, date=now)
    >>> statement_line = statement.lines.new()
    >>> statement_line.date = now
    >>> statement_line.description = 'Customer Invoice Bank Discount reception'
    >>> statement_line.amount = Decimal('100.0')
    >>> statement.save()
    >>> statement.click('confirm')
    >>> statement.state
    u'confirmed'

Create transaction lines on statement line and post it::

    >>> statement_line, = statement.lines
    >>> st_move_line = statement_line.lines.new()
    >>> st_move_line.payment = payment
    >>> st_move_line.amount
    Decimal('100.0')
    >>> st_move_line.account.name
    u'Customers Bank Discount'
    >>> st_move_line.party.name
    u'Customer'
    >>> statement_line.save()
    >>> statement_line.click('post')

The statement's amount is in Customers Bank Discount account debit::

    >>> customer_bank_discounts.reload()
    >>> customer_bank_discounts.balance
    Decimal('-100.00')

When the invoice due date plus some margin days arrives, if the bank doesn't
substract the advanced amount is because the payment succeeded::

    >>> payment.click('succeed')
    >>> payment.clearing_move != None
    True

Now, the invoice is paid, the customer's due amount is zero, also owr due with
bank::

    >>> customer_invoice.reload()
    >>> customer_invoice.state
    u'paid'
    >>> receivable.reload()
    >>> receivable.balance
    Decimal('0.00')
    >>> customer_bank_discounts.reload()
    >>> customer_bank_discounts.balance
    Decimal('0.00')

But if after that, the bank substracts the advanced amount, we create the bank
statement::

    >>> statement2 = BankStatement(journal=statement_journal, date=now)
    >>> statement_line = statement2.lines.new()
    >>> statement_line.date = now
    >>> statement_line.description = 'Customer Invoice Bank Discount recover'
    >>> statement_line.amount = Decimal('-100.0')
    >>> statement2.save()
    >>> statement2.click('confirm')
    >>> statement2.state
    u'confirmed'

Create transaction lines on statement line and post it::

    >>> statement_line2, = statement2.lines
    >>> st_move_line = statement_line2.lines.new()
    >>> st_move_line.payment = payment
    >>> st_move_line.amount
    Decimal('-100.0')
    >>> st_move_line.account.name
    u'Customers Bank Discount'
    >>> st_move_line.party.name
    u'Customer'
    >>> statement_line2.save()
    >>> statement_line2.click('post')

The payment is failed, clearing move reverted so amount is due by customer and
we doesn't have cash::

    >>> payment.reload()
    >>> payment.state
    u'failed'
    >>> payment.clearing_move == None
    True
    >>> customer_invoice.reload()
    >>> customer_invoice.state
    u'posted'
    >>> receivable.reload()
    >>> receivable.balance
    Decimal('100.00')
    >>> customer_bank_discounts.reload()
    >>> customer_bank_discounts.balance
    Decimal('0.00')
    >>> cash.reload()
    >>> cash.balance
    Decimal('0.00')

But finally, the customer pays the invoice directly::

    >>> statement3 = BankStatement(journal=statement_journal, date=now)
    >>> statement_line = statement3.lines.new()
    >>> statement_line.date = now
    >>> statement_line.description = 'Customer Invoice payment'
    >>> statement_line.amount = Decimal('100.0')
    >>> statement3.save()
    >>> statement3.click('confirm')
    >>> statement3.state
    u'confirmed'

Create transaction lines on statement line and post it::

    >>> statement_line3, = statement3.lines
    >>> st_move_line = statement_line3.lines.new()
    >>> st_move_line.invoice = customer_invoice
    >>> st_move_line.amount
    Decimal('100.0')
    >>> st_move_line.account.name
    u'Main Receivable'
    >>> st_move_line.party.name
    u'Customer'
    >>> statement_line3.save()
    >>> statement_line3.click('post')

So the payment is succeeded, the invoice paid again and due amounts are 0::

    >>> customer_invoice.reload()
    >>> customer_invoice.state
    u'paid'
    >>> receivable.reload()
    >>> receivable.balance
    Decimal('0.00')
    >>> customer_bank_discounts.reload()
    >>> customer_bank_discounts.balance
    Decimal('0.00')

Create two customer invoices::

    >>> customer_invoice2 = Invoice(type='out_invoice')
    >>> customer_invoice2.party = customer
    >>> customer_invoice2.payment_term = payment_term
    >>> invoice_line = customer_invoice2.lines.new()
    >>> invoice_line.quantity = 1
    >>> invoice_line.unit_price = Decimal('200')
    >>> invoice_line.account = revenue
    >>> invoice_line.description = 'Test 2'
    >>> customer_invoice2.save()
    >>> customer_invoice2.click('post')
    >>> customer_invoice2.state
    u'posted'

    >>> customer_invoice3 = Invoice(type='out_invoice')
    >>> customer_invoice3.party = customer
    >>> customer_invoice3.payment_term = payment_term
    >>> invoice_line = customer_invoice3.lines.new()
    >>> invoice_line.quantity = 1
    >>> invoice_line.unit_price = Decimal('80')
    >>> invoice_line.account = revenue
    >>> invoice_line.description = 'Test 3'
    >>> customer_invoice3.save()
    >>> customer_invoice3.click('post')
    >>> customer_invoice3.state
    u'posted'

    >>> receivable.reload()
    >>> receivable.balance
    Decimal('280.00')

Create a payment with 80% bank discount for first of them::

    >>> line, = [l for l in customer_invoice2.move.lines
    ...     if l.account == receivable]
    >>> pay_line = Wizard('account.move.line.pay', [line])
    >>> pay_line.form.journal = payment_receivable_80_journal
    >>> pay_line.execute('pay')
    >>> payment2, = Payment.find([('state', '=', 'draft')])
    >>> payment2.amount
    Decimal('200.00')
    >>> payment2.click('approve')
    >>> payment2.state
    u'approved'
    >>> process_payment = Wizard('account.payment.process', [payment2])
    >>> process_payment.execute('process')
    >>> payment2.reload()
    >>> payment2.state
    u'processing'

And another payment with 100% bank discount for the second one::

    >>> line, = [l for l in customer_invoice3.move.lines
    ...     if l.account == receivable]
    >>> pay_line = Wizard('account.move.line.pay', [line])
    >>> pay_line.form.journal = payment_receivable_100_journal
    >>> pay_line.execute('pay')
    >>> payment3, = Payment.find([('state', '=', 'draft')])
    >>> payment3.amount
    Decimal('80.00')
    >>> payment3.click('approve')
    >>> payment3.state
    u'approved'
    >>> process_payment = Wizard('account.payment.process', [payment3])
    >>> process_payment.execute('process')
    >>> payment3.reload()
    >>> payment3.state
    u'processing'

Create and confirm bank statement::

    >>> statement4 = BankStatement(journal=statement_journal, date=now)
    >>> statement_line = statement4.lines.new()
    >>> statement_line.date = now
    >>> statement_line.description = 'Bank Discount for second invoice'
    >>> statement_line.amount = Decimal('160.0')
    >>> statement_line = statement4.lines.new()
    >>> statement_line.date = now
    >>> statement_line.description = 'Bank Discount for third invoice'
    >>> statement_line.amount = Decimal('80.0')
    >>> statement4.save()
    >>> statement4.click('confirm')
    >>> statement4.state
    u'confirmed'

Create transaction lines on statement lines and post them::

    >>> statement_line4, statement_line5 = statement4.lines
    >>> st_move_line = statement_line4.lines.new()
    >>> st_move_line.payment = payment2
    >>> st_move_line.amount
    Decimal('160.0')
    >>> st_move_line.account.name
    u'Customers Bank Discount'
    >>> st_move_line.party.name
    u'Customer'
    >>> statement_line4.save()
    >>> statement_line4.click('post')
    >>> st_move_line = statement_line5.lines.new()
    >>> st_move_line.payment = payment2
    >>> st_move_line.amount
    Decimal('80.0')
    >>> st_move_line.account.name
    u'Customers Bank Discount'
    >>> st_move_line.party.name
    u'Customer'
    >>> statement_line5.save()
    >>> statement_line5.click('post')

All the amount is on cash account and as debit with bank::

    >>> cash.reload()
    >>> cash.balance
    Decimal('340.00')
    >>> customer_bank_discounts.reload()
    >>> customer_bank_discounts.balance
    Decimal('-240.00')

When the invoices due date arrives, the pending amount of second invoice is
paid by customer but bank substract the third invoice amount::

    >>> statement5 = BankStatement(journal=statement_journal, date=now)
    >>> statement_line = statement5.lines.new()
    >>> statement_line.date = now
    >>> statement_line.description = 'Pending payment of second invoice'
    >>> statement_line.amount = Decimal('40.0')
    >>> statement_line = statement5.lines.new()
    >>> statement_line.date = now
    >>> statement_line.description = 'Recover of Bank Discount for third invoice'
    >>> statement_line.amount = Decimal('-80.0')
    >>> statement5.save()
    >>> statement5.click('confirm')
    >>> statement5.state
    u'confirmed'

Create transaction line on statement line with pending amount of second
invoice, selecting the invoice and the payment::

    >>> statement_line6, statement_line7 = statement5.lines
    >>> st_move_line = statement_line6.lines.new()
    >>> st_move_line.invoice = customer_invoice2
    >>> st_move_line.payment == payment2
    True
    >>> st_move_line.amount
    Decimal('40.0')
    >>> st_move_line.account.name
    u'Main Receivable'
    >>> st_move_line.party.name
    u'Customer'
    >>> statement_line6.save()
    >>> statement_line6.click('post')

The payment of second customer invoice is succeeded::

    >>> payment2.reload()
    >>> payment2.state
    u'succeeded'
    >>> customer_invoice2.reload()
    >>> customer_invoice2.state
    u'paid'

Create transaction line on statement line with recovering of bank discount for
third invoice selecting the payment::

    >>> st_move_line = statement_line7.lines.new()
    >>> st_move_line.payment = payment3
    >>> st_move_line.amount
    Decimal('-80.0')
    >>> st_move_line.account.name
    u'Customers Bank Discount'
    >>> st_move_line.party.name
    u'Customer'
    >>> statement_line7.save()
    >>> statement_line7.click('post')

And the payment of third customer invoice is failed::

    >>> payment3.reload()
    >>> payment3.state
    u'failed'
    >>> customer_invoice3.reload()
    >>> customer_invoice3.state
    u'posted'

The third invoice amount is also owed, the due with bank is empty and the cash
do not have the third invoice amount::

    >>> receivable.reload()
    >>> receivable.balance
    Decimal('80.00')
    >>> customer_bank_discounts.reload()
    >>> customer_bank_discounts.balance
    Decimal('0.00')
    >>> cash.reload()
    >>> cash.balance
    Decimal('300.00')
