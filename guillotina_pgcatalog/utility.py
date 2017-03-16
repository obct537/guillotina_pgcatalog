# -*- coding: utf-8 -*-
from guillotina import configure
from guillotina.catalog.catalog import DefaultSearchUtility
from guillotina.interfaces import ICatalogUtility
from guillotina.utils import get_content_path
from guillotina.utils import get_current_request
from guillotina_pgcatalog import schema

import json
import logging


logger = logging.getLogger('guillotina_pgcatalog')


@configure.utility(provides=ICatalogUtility)
class PGSearchUtility(DefaultSearchUtility):
    """
    Indexes are transparently maintained in the database so all indexing
    operations can be ignored
    """

    async def get_data(self, content):
        # we can override and ignore this request since data is already
        # stored in db...
        return {}

    async def search(self, site, query):
        """
        XXX transform into el query
        """
        pass

    async def query(self, site, query, request=None):
        """
        transform into query...
        right now, it's just passing through into elasticsearch
        """

        # this data needs to be careful verified because we can't use prepared
        # placeholders for it.
        try:
            limit = int(query.pop('limit', 20))
        except:
            limit = 20
        page = query.pop('page', 1)
        order = query.pop('order', 'zoid')  # need some ordering to ensure paging works
        if order not in [k for k in schema.get_indexes().keys()] + ['zoid']:
            order = 'zoid'
        try:
            skip = (int(page) - 1) * limit
        except:
            skip = 0

        sql_arguments = []
        sql_wheres = []
        for field_name, value in query.items():
            index = schema.get_index(field_name)
            sql_arguments.append(value)
            sql_wheres.append(index.where(arg_idx=len(sql_arguments)))

        # ensure we only query this site
        site_path = get_content_path(site)
        sql_wheres.append("""substring(json->>'path', 0, {}) = '{}'""".format(
            len(site_path) + 1,
            site_path
        ))

        sql = '''select zoid, json
                 from objects
                 where {}
                 order by {}
                 limit {} offset {}'''.format(
                    ' AND '.join(sql_wheres),
                    order,
                    limit,
                    skip)
        sql_count = '''select count(*)
                       from objects
                       where {}'''.format(' AND '.join(sql_wheres))

        conn = self.get_conn()
        smt = await conn.prepare(sql)
        smt_count = await conn.prepare(sql_count)
        count_result = await smt_count.fetchrow(*sql_arguments)

        results = []
        async for record in smt.cursor(*sql_arguments):
            data = json.loads(record['json'])
            results.append(data)
        return {
            'items_count': count_result['count'],
            'member': results,
            'page': page
        }

    def get_conn(self):
        request = get_current_request()
        return request._tm._txn._db_conn

    async def index(self, site, datas):
        pass

    async def remove(self, site, uids):
        pass

    async def initialize_catalog(self, site):
        conn = self.get_conn()
        for name, index in schema.get_indexes().items():
            await conn.execute('''DROP INDEX IF EXISTS {}'''.format(index.idx_name))
            await conn.execute(index.index_sql)
