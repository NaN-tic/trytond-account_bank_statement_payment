# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from sql import Column
from sql.aggregate import Max

from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.tools import grouped_slice, reduce_ids
from trytond.transaction import Transaction

__all__ = ['MoveLine']


class MoveLine(metaclass=PoolMeta):
    __name__ = 'account.move.line'
    payment_group = fields.Function(fields.Many2One('account.payment.group',
            'Payment Group'),
        'get_payment_fields', searcher='search_payment_fields')
    payment_date = fields.Function(fields.Date('Payment Date'),
        'get_payment_fields', searcher='search_payment_fields')

    @classmethod
    def get_payment_fields(cls, lines, name):
        pool = Pool()
        Payment = pool.get('account.payment')
        table = Payment.__table__()
        cursor = Transaction().connection.cursor()

        line_ids = [l.id for l in lines]
        result = {}.fromkeys(line_ids, None)

        for sub_ids in grouped_slice(line_ids):
            query = table.select(table.line, Max(Column(table, name[8:])),
                where=((table.state != 'failed')
                    & reduce_ids(table.line, sub_ids)), group_by=table.line)
            cursor.execute(*query)
            result.update(dict(cursor.fetchall()))
        return result

    @classmethod
    def search_payment_fields(cls, name, clause):
        return [('payments.%s' % name[8:],) + tuple(clause[1:])]
