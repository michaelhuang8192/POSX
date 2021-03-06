import json
import os
import time
import config
import re
import datetime
import traceback


CFG = {
    'id': 'sync_6F5E0966',
    'name': 'Sync',
    'perm_list': [
    ('access', ''),
    ],
}


REC_FLAG_ACCEPTED = 1 << 0
REC_FLAG_PARTIAL = 1 << 6

Delivery = App.load('/request/delivery')

DEFAULT_PERM = 0x00000001
class RequestHandler(App.load('/advancehandler').RequestHandler):
    

    def fn_search_by_docnum(self):
        num = self.req.qsv_ustr('term')
        cur = self.cur()

        rs = []

        cur.execute("select sid,sid_type,global_js from sync_receipts where num=%s order by sid desc", (num,))
        cnz = cur.column_names
        for r in cur.fetchall():
            gjs = r[2] and json.loads(r[2]) or {}
            a = {'type': 0, 'sid': str(r[0]), 'sid_type': r[1], 'txt': (gjs.get('customer') or {}).get('company', '')}
            rs.append(a)

        cur.execute("select sid,(status>>16) as deleted,global_js from sync_salesorders where sonum=%s order by deleted asc,sid desc", (num,))
        cnz = cur.column_names
        for r in cur.fetchall():
            gjs = r[2] and json.loads(r[2]) or {}
            a = {'type': 1, 'sid': str(r[0]), 'txt': (gjs.get('customer') or {}).get('company', '')}
            rs.append(a)

        cur.execute("select sid,(status>>16) as deleted,global_js from sync_purchaseorders where ponum=%s order by deleted asc,sid desc", (num,))
        cnz = cur.column_names
        for r in cur.fetchall():
            gjs = r[2] and json.loads(r[2]) or {}
            a = {'type': 2, 'sid': str(r[0]), 'txt': gjs.get('vend', '')}
            rs.append(a)

        cur.execute("select sid,global_js from sync_vouchers where num=%s order by sid desc", (num,))
        cnz = cur.column_names
        for r in cur.fetchall():
            gjs = r[1] and json.loads(r[1]) or {}
            a = {'type': 3, 'sid': str(r[0]), 'txt': gjs.get('vend', '')}
            rs.append(a)

        self.req.writejs(rs)


    def fn_get_items_by_nums(self):
        nums = map(str, map(int, self.req.psv_str('nums').split('|')))[:5000]

        items = {}

        cur = self.cur()
        cur.execute('select sid,num,name,detail from sync_items where num in (%s)' % (','.join(nums),))
        
        for r in cur.fetchall():
            gjs = json.loads(r[3])
            items[ str(r[0]) ] = {
            'name': r[2],
            'num': r[1],
            'alu': gjs['units'][0][1]
            }

        self.req.writejs(items)

    def fn_get_items(self):
        sids = map(str, map(int, self.req.psv_str('sids').split('|')))[:5000]

        items = {}

        cur = self.cur()
        cur.execute('select sid,num,name,detail from sync_items where sid in (%s)' % (','.join(sids),))
        
        for r in cur.fetchall():
            gjs = json.loads(r[3])
            items[ str(r[0]) ] = {
            'name': r[2],
            'num': r[1],
            'alu': gjs['units'][0][1]
            }

        self.req.writejs(items)

    def fn_get_item(self):
        row = self.get_item( self.qsv_int('item_no') )
        if not row: return
        self.req.writejs(row)
    
    def fn_search_item__simple(self):
        kw = self.qsv_str('term')
        if not kw: return
        mode = self.qsv_int('mode')
        
        items = self.search_item(kw, mode)
        for t in items:
            js = t[3] = json.loads(t[3])
            for u in js['units']: u[0] = None
            del js['udfs']
        
        self.req.writejs(items)
    fn_search_item__simple.PERM = 0
    
    def fn_itemsearch(self):
        kw = self.qsv_str('term')
        if not kw: return
        mode = self.qsv_int('mode')
        mini = self.qsv_int('mini')
        self.req.writejs( self.search_item(kw, mode, mini and 4 or 10) )
        
    def fn_adv_item_srch(self):
        kw = self.qsv_str('term')
        if not kw: return
        mode = self.qsv_int('mode')
        self.req.writejs( self.search_item(kw, mode, 100) )
    fn_adv_item_srch.PERM = 1 << config.USER_PERM_BIT['admin']
    
    def fn_custsearch(self):
        kw = self.qsv_str('term')
        if not kw: return
        mode = self.qsv_int('mode')
        
        self.req.writejs( self.search_cust(kw, mode) )

    def fn_adv_cust_srch(self):
        kw = self.qsv_str('term')
        if not kw: return
        mode = self.qsv_int('mode')
        self.req.writejs( self.search_cust(kw, mode, 100) )
    #fn_adv_cust_srch.PERM = 1 << config.USER_PERM_BIT['admin']

    def fn_sync(self):
        uts = self.getconfig(config.cid__sync_last_update)
        self.req.writejs({'sync': int(time.time()) - uts <= 7})
    
    def fn_getcustorders(self):
        cid = self.qsv_int('cid', None)
        if cid == None: return
        pgsz = self.qsv_int('pagesize')
        sidx = self.qsv_int('sidx')
        eidx = self.qsv_int('eidx')
    
        ord_flag = self.qsv_int('flag')
        
        if pgsz > 100 or eidx - sidx > 5: return
        
        db = self.db()
        cur = db.cur()
        
        rpg = {}
        if pgsz > 0 and sidx >= 0 and sidx < eidx:
            cur.execute('select SQL_CALC_FOUND_ROWS sso.sid,sso.status,sso.sonum,sso.clerk,sso.sodate,sso.global_js,so.delivery_date from sync_salesorders sso left join salesorder so on (sso.sid=so.sid) where sso.cust_sid=%d%s order by sso.sid desc limit %d,%d' % (
                cid, ord_flag == 0 and ' and sso.status=0' or '',
                sidx * pgsz, (eidx - sidx) * pgsz
                )
            )
            d = cur.fetchall()
            for i in range(sidx, eidx): rpg[i] = []
            if d:
                k = 0
                for r in d:
                    s = int(r[1])
                    g = json.loads(r[5])
                    customer = g['customer']
                    if r[6]:
                        m_r,m_day = divmod(r[6], 100)
                        m_year,m_month = divmod(m_r, 100)
                        m_mdy = '%02d/%02d/%04d' % (m_month, m_day, m_year)
                    else:
                        m_mdy = ''
                    r = [
                        r[2],
                        r[3],
                        g['qtycount'], g['sentcount'],
                        g['total'],
                        time.strftime("%m/%d/%Y", time.localtime(int(r[4]))),
                        m_mdy,
                        str(r[0])
                    ]
                    rpg[sidx].append(r)
                    k += 1
                    if k == pgsz:
                        sidx += 1
                        k = 0
                        
            cur.execute('select FOUND_ROWS()')
        else:
            cur.execute('select count(*) from sync_salesorders where cust_sid=%d%s' % (
                cid, ord_flag == 0 and ' and status=0' or '',
                )
            )
        rlen = int(cur.fetchall()[0][0])
        
        self.req.writejs( {'res':{'len':rlen, 'rpg':rpg}} )
        
    
    ORDER_CLS = [None, ['po', 'purchaseorders', 'vend'], ['so', 'salesorders', 'cust']]
    def fn_getitemorders(self):
        rid = self.qsv_int('rid', None)
        if rid == None: return
        pgsz = self.qsv_int('pagesize')
        sidx = self.qsv_int('sidx')
        eidx = self.qsv_int('eidx')
    
        ord_type = self.qsv_int('type')
        cls = self.ORDER_CLS[ord_type]
        if not cls: return
        
        ord_flag = self.qsv_int('flag')
        
        if pgsz > 100 or eidx - sidx > 5: return
        
        db = self.db()
        cur = db.cur()
        
        rpg = {}
        if pgsz > 0 and sidx >= 0 and sidx < eidx:
            cur.execute('select SQL_CALC_FOUND_ROWS i.*,s.'+cls[0]+'num,s.clerk,s.'+cls[0]+'date,s.'+cls[2]+'_sid from sync_link_item i left join sync_'+cls[1]+' s on (s.sid=i.doc_sid) where i.item_sid=%d and i.doc_type=%d%s order by i.doc_sid desc limit %d,%d' % (
                rid, ord_type, ord_flag == 0 and ' and i.flag=0' or '',
                sidx * pgsz, (eidx - sidx) * pgsz
                )
            )
            d = cur.fetchall()
            for i in range(sidx, eidx): rpg[i] = []
            if d:
                k = 0
                for r in d:
                    r = [
                        r[7], r[6], r[8],
                        int(r[4]), int(r[5]),
                        time.strftime("%m/%d/%Y", time.localtime(int(r[9]))),
                        str(r[1]), int(r[2]), str(r[10])
                    ]
                    rpg[sidx].append(r)
                    k += 1
                    if k == pgsz:
                        sidx += 1
                        k = 0
        
            cur.execute('select FOUND_ROWS()')
        else:
            cur.execute('select count(*) from sync_link_item where item_sid=%d and doc_type=%d%s' % (
                rid, ord_type, ord_flag == 0 and ' and flag=0' or '',
                )
            )
        rlen = int(cur.fetchall()[0][0])
        
        self.req.writejs( {'res':{'len':rlen, 'rpg':rpg}} )
        
    def fn_printorder(self):
        rid = self.qsv_int('rid', None)
        if rid == None: return
    
        ord_type = self.qsv_int('type')
        
        if ord_type == 1:
            self.print_po(rid)
        elif ord_type == 2:
            self.print_so(rid)
        elif ord_type == 3:
            self.print_vo(rid)
            
    def print_po(self, rid):
        db = self.db()
        cur = db.cur()
        db_col_nzs = ('r_sid', 'r_vend_sid', 'r_status', 'r_ponum', 'r_clerk', 'r_podate', 'r_shipdate', 'r_duedate', 'r_creationdate', 'r_global', 'r_items')
        cur.execute('select * from sync_purchaseorders where sid=%d' % (rid,))
        r = cur.fetchall()
        if not r: return
        r = dict(zip(db_col_nzs, r[0]))
        
        r['r_status'] = int(r['r_status'])
        r['r_podate'] = time.strftime("%m/%d/%Y %I:%M:%S %p", time.localtime(int(r['r_podate'])))
        r['r_creationdate'] = time.strftime("%m/%d/%Y %I:%M:%S %p", time.localtime(int(r['r_creationdate'])))
        
        r['r_global'] = json.loads(r['r_global'])
        r['r_items'] = json.loads(r['r_items'])
        
        if r['r_global']['canceldate']:
            r['r_canceldate'] = time.strftime("%m/%d/%Y %I:%M:%S %p", time.localtime(int(r['r_global']['canceldate'])))
        else:
            r['r_canceldate'] = ''
            
        r['auto_print'] = self.qsv_int('auto_print')
        
        r['round_ex'] = config.round_ex
        
        self.req.writefile('po_print_v2.html', r)
    
    def fn_has_salesorder(self):
        rno = self.req.qsv_ustr('rno')
        cur = self.cur()
        cur.execute('select sid from sync_salesorders where sonum=%s order by status asc,sid desc', (rno,))
        rows = cur.fetchall()
        if not rows: return
        self.req.writejs({'sid': str(rows[0][0])})
    
    def fn_print_so_by_num(self):
        rno = self.req.qsv_ustr('rno')
        cur = self.cur()
        cur.execute('select sid from sync_salesorders where sonum=%s order by status asc,sid desc', (rno,))
        rows = cur.fetchall()
        if not rows: return

        self.print_so(rows[0][0])

    fn_print_so_by_num.PERM = 0

    def print_so(self, rid):
        db = self.db()
        cur = db.cur()
        db_col_nzs = ('r_sid', 'r_cust_sid', 'r_status', 'r_price_level', 'r_sonum', 'r_clerk', 'r_cashier', 'r_sodate', 'r_duedate', 'r_creationdate', 'r_global', 'r_items')
        cur.execute('select * from sync_salesorders where sid=%d' % (rid,))
        r = cur.fetchall()
        if not r: return
        r = dict(zip(db_col_nzs, r[0]))
        
        r['r_price_level'] = int(r['r_price_level'])
        r['r_status'] = int(r['r_status'])
        r['r_sodate'] = time.strftime("%m/%d/%Y", time.localtime(int(r['r_sodate'])))
        r['r_creationdate'] = time.strftime("%m/%d/%Y %I:%M:%S %p", time.localtime(int(r['r_creationdate'])))
        
        r['r_global'] = json.loads(r['r_global'])
        r['r_items'] = json.loads(r['r_items'])
        
        r['auto_print'] = self.qsv_int('auto_print')
        
        cur.execute('select sid,sid_type,num from sync_receipts where so_sid=%s order by sid asc',(
            r['r_sid'],
            )
        )
        nzs = cur.column_names
        r['r_ref_receipts'] = [ dict(zip(nzs, f_row)) for f_row in cur.fetchall() ]
        
        r['d_notes'] = d_notes = []
        cur.execute('select dn_ts,dn_flag,dn_val,(select user_name from user where user_id=dn_uid limit 1) as dn_unz from doc_note where doc_type=%s and doc_sid=%s order by dn_id desc limit 50', (
                    0, r['r_sid']
            )
        )
        for rr in cur.fetchall():
            rr = list(rr)
            rr[0] = time.strftime("%m/%d/%y %I:%M %p", time.localtime(rr[0]))
            d_notes.append(rr)
        
        r['r_delivery_date'] = ''
        cur.execute('select delivery_date,delivery_zip from salesorder where sid=%s and delivery_date!=0', (r['r_sid'],))
        rows = cur.fetchall()
        if rows:
            r_delivery_date = rows[0][0]
            m_r,m_day = divmod(r_delivery_date, 100)
            m_year,m_month = divmod(m_r, 100)
            r['r_delivery_date'] = "%02d/%02d/%04d" % (m_month, m_day, m_year)
            r['r_delivery_zip'] = '%05d' % rows[0][1]
        
        r['round_ex'] = config.round_ex
        r['price_lvls'] = config.PRICE_LEVELS
        
        r['users_lku'] = dict([ x[:2] for x in self.getuserlist() ])
        
        sc_d = {}
        r['sc_l'] = sc_l = []
        cur.execute('select sc_id,sc_flag,sc_date,sc_note from schedule where doc_type=0 and doc_sid=%s order by sc_id desc', (r['r_sid'],))
        nzs = cur.column_names
        for x in cur.fetchall():
            x = dict(zip(nzs, x))
            sc_l.append(x)
            sc_d[ x['sc_id'] ] = x
            
            x['drs'] = []

            m,d = divmod(x['sc_date'], 100)
            y,m = divmod(m, 100)
            x['dt_s'] = '%02d/%02d/%02d' % (m, d, y)
            
            x['sc_name'] = '%s - %s' % (
                x['sc_flag'] & REC_FLAG_PARTIAL and 'Partial' or 'Complete',
                x['sc_flag'] & REC_FLAG_ACCEPTED and 'Accepted' or 'Pending',
            )
        
        r['non_sc_l'] = non_sc_l = []
        if r['r_ref_receipts']:
            cur.execute('select r.*,d.name,d.ts from deliveryv2_receipt r left join deliveryv2 d on (r.d_id=d.d_id) where r.num in (%s) order by r.d_id desc' % (
                ','.join([ str(f_v['num']) for f_v in r['r_ref_receipts'] ]),
                )
            )
            nzs = cur.column_names
            for x in cur.fetchall():
                x = dict(zip(nzs, x))
                
                sc = sc_d.get(x['sc_id'])
                if sc:
                    sc['drs'].append(x)
                else:
                    non_sc_l.append(x)
                
                dt = datetime.date.fromtimestamp(x['ts'])
                x['dt_s'] = dt.strftime('%m/%d/%Y')
                x['dt_i'] = dt.year * 10000 + dt.month * 100 + dt.day
                
                if x['problem_flag']:
                    js = x['js'] and json.loads(x['js']) or {}
                    pbs = js.get('problems')
                    x['problem_s'] = ', '.join([ Delivery.PROBLEMS[int(f_i)] + (f_v[1] and ': ' + f_v[1] or '') for f_i,f_v in pbs.items() ])
            
        
        self.req.writefile(self.qsv_int('simple') and 'so_print_v2_simple.html' or 'so_print_v2.html', r)

    def print_vo(self, rid):
        db = self.db()
        cur = db.cur()
        db_col_nzs = ('r_sid', 'r_vend_sid', 'r_ref_sid', 'r_flag', 'r_num', 'r_clerk', 'r_voucherdate', 'r_duedate', 'r_invdate', 'r_creationdate', 'r_global', 'r_items')
        cur.execute('select * from sync_vouchers where sid=%d' % (rid,))
        r = cur.fetchall()
        if not r: return
        r = dict(zip(db_col_nzs, r[0]))
        
        r['r_flag'] = int(r['r_flag'])
        r['r_voucherdate'] = time.strftime("%m/%d/%Y %I:%M:%S %p", time.localtime(int(r['r_voucherdate'])))
        r['r_creationdate'] = time.strftime("%m/%d/%Y %I:%M:%S %p", time.localtime(int(r['r_creationdate'])))
        r['r_duedate'] = r['r_duedate'] and time.strftime("%m/%d/%Y", time.localtime(int(r['r_duedate']))) or ''
        r['r_invdate'] = r['r_invdate'] and time.strftime("%m/%d/%Y", time.localtime(int(r['r_invdate']))) or ''
        
        r['r_global'] = json.loads(r['r_global'])
        r['r_items'] = json.loads(r['r_items'])
        
        r['auto_print'] = self.qsv_int('auto_print')
        
        r['round_ex'] = config.round_ex
        
        porefs = {}
        for i in r['r_items']:
            if i['porefsid'] == None: continue
            porefs[ str(i['porefsid']) ] = True
            
        po = []
        if porefs:
            cur.execute('select sid,ponum,clerk,podate from sync_purchaseorders where sid in (%s) order by sid desc' % (','.join(porefs),))
            for i in cur.fetchall():
                po.append( [i[0],] + list(i[1:3]) + [time.strftime("%m/%d/%Y", time.localtime(int(i[3])))] )
        r['r_po'] = po
        
        self.req.writefile('vo_print_v2.html', r)


    def fn_get_doc_item_list_min(self):
        doc_type = self.qsv_int('doc_type')
        doc_sid = self.qsv_int('doc_sid')

        cur = self.cur()
        if doc_type:
            cur.execute('select items_js from sync_salesorders where sid=%s', (doc_sid, ))
        else:
            cur.execute('select items_js from sync_receipts where sid_type=0 and sid=%s', (doc_sid, ))
        
        items = []
        for t in json.loads(cur.fetchall()[0][0]):
            items.append((t['itemno'], t['alu'], t['desc1'], t['qty'], t['uom'], '$%0.2f' % t['price']))

        self.req.writejs(items)

