import json
import os
import time
import config
import re
import datetime
import traceback
import bisect
import tools
import const
import cPickle

Receipt = App.load('/request/receipt')
Delivery = App.load('/request/delivery')
DEFAULT_PERM = 0x00000001
class RequestHandler(App.load('/basehandler').RequestHandler):
    
    def fn_default(self):
        self.req.writefile('hist_receipts.html')
    
    def fn_search(self):
        self.req.writefile('receipt_search.html')
    
    def fn_srch_item_with_cid(self):
        kw = self.qsv_str('term')
        if not kw: return
        mode = self.qsv_int('mode')
        
        cid = self.qsv_int('cid', None)
        if cid == None: return
        
        kws = set(self.regx_kw.sub(u' ', kw).strip().lower().replace(u',', u' ').strip().split(u' '))
        kws.discard(u'')
        if not kws: return
        
        db = self.db()
        cur = db.cur()
        
        cur.execute('select distinct h.itemsid from sync_receipts r left join sync_items_hist h on (r.sid=h.docsid and r.sid_type=h.sid_type and (h.flag>>8)<2) where r.cid=%d and h.itemsid is not null and h.itemsid != 1000000005' % (cid,))
        sids = cur.fetchall()
        if not sids: return
        
        if mode:
            kw = '+' + u' +'.join([k for k in kws])
        else:
            kw = '+' + u' +'.join([k + '* ' + k for k in kws])
        qs = "select sid,num,name,detail,(match(lookup,name) against (%%s in boolean mode) + match(lookup) against (%%s in boolean mode)*2) as pos from sync_receipts_items where match(lookup,name) against (%%s in boolean mode) and sid in (%s) order by pos desc,num asc limit 10" % (','.join([str(x[0]) for x in sids]),)
        cur.execute(qs, (kw, kw.replace(u'+', u''), kw))
        
        #self.req.exitjs({'qs': qs, 'vs': (kw, kw.replace(u'+', u''), kw, cid)})
        
        res = [ [str(x[0]),] + list(x[1:]) for x in cur.fetchall() ]
        
        self.req.writejs(res)
    
    def fn_get_srch_items(self):
        ret = {'res':{'len':0, 'apg':[]}}
        tid = self.qsv_int('tid', None)
        if tid == None: self.req.exitjs(ret)
        cid = self.qsv_int('cid', None)
        if cid == None: self.req.exitjs(ret)
        
        pgsz = self.qsv_int('pagesize')
        sidx = self.qsv_int('sidx')
        eidx = self.qsv_int('eidx')
        if pgsz > 100 or eidx - sidx > 5: self.req.exitjs(ret)
        
        db = self.db()
        cur = db.cur()
        apg = []
        if pgsz > 0 and sidx >= 0 and sidx < eidx:
            cur.execute('select SQL_CALC_FOUND_ROWS h.docnum,h.docdate,h.qtydiff,h.extprice,h.doctxt,h.docsid,h.sid_type from sync_receipts r left join sync_items_hist h on (r.sid=h.docsid and r.sid_type=h.sid_type and h.itemsid=%d and (h.flag>>8)<2) where r.cid=%d and h.itemsid is not null and h.itemsid != 1000000005 order by h.docdate desc,r.sid asc limit %d,%d' % (
                        tid, cid,
                        sidx * pgsz, (eidx - sidx) * pgsz
                        )
            )
            for r in cur.fetchall():
                r = list(r)
                r[5] = str(r[5])
                r[2] = -r[2]
                r[3] = not r[2] and ' ' or '%0.2f' % (r[3] / r[2],)
                r[1] = time.strftime("%m/%d/%Y %I:%M:%S %p", time.localtime(r[1])),
                apg.append(r)
        
            cur.execute('select FOUND_ROWS()')
            
        else:
            cur.execute('select count(*) from sync_receipts r left join sync_items_hist h on (r.sid=h.docsid and r.sid_type=h.sid_type and h.itemsid=%d and (h.flag>>8)<2) where r.cid=%d and h.itemsid is not null and h.itemsid != 1000000005' % (
                        tid, cid,
                        )
            )
            
        rlen = int(cur.fetchall()[0][0])
        res = ret['res']
        res['len'] = rlen
        res['apg'] = apg
        self.req.writejs(ret)
    
    
    def fn_get_cust_items(self):
        ret = {'res':{'len':0, 'apg':[]}}
        cid = self.qsv_int('cid')
        
        pgsz = self.qsv_int('pagesize')
        sidx = self.qsv_int('sidx')
        eidx = self.qsv_int('eidx')
        if pgsz > 100 or eidx - sidx > 5: self.req.exitjs(ret)
        
        cur = self.cur()
        apg = []
        perm = self.user_lvl & (1 << config.USER_PERM_BIT['item stat access'])
        if pgsz > 0 and sidx >= 0 and sidx < eidx:
            cur.execute('select SQL_CALC_FOUND_ROWS i.num,i.detail,i.name,sum(h.qtydiff) as total_qty,0,max(h.docdate) as last_docdate,h.itemsid,count(*),(max(h.docdate)&(~0x7ffff)|count(*)) as pos from sync_receipts r left join sync_items_hist h on (r.sid=h.docsid and r.sid_type=h.sid_type and (h.flag>>8)<2) left join sync_receipts_items i on (h.itemsid=i.sid) where r.cid=%d and h.itemsid is not null and h.itemsid != 1000000005 group by h.itemsid order by pos desc,h.itemsid asc limit %d,%d' % (
                cid, sidx * pgsz, (eidx - sidx) * pgsz
                )
            )
            for r in cur.fetchall():
                r = list(r)
                r[4] = 'Find(%d)' % (r[7],)
                r[5] = time.strftime("%m/%d/%Y %I:%M:%S %p", time.localtime(r[5]))
                r[6] = str(r[6])
                r[3] = '%0.1f' % (r[3], )
                if not perm: r[3] = ''
                r[1] = json.loads(r[1]).get('alu', '')
                apg.append(r)
        
            cur.execute('select FOUND_ROWS()')
            
        else:
            cur.execute('select count(*) from sync_receipts r left join sync_items_hist h on (r.sid=h.docsid and r.sid_type=h.sid_type and (h.flag>>8)<2) where r.cid=%d and h.itemsid is not null and h.itemsid != 1000000005 group by h.itemsid' % (
                cid,
                )
            )
            
        rlen = int(cur.fetchall()[0][0])
        res = ret['res']
        res['len'] = rlen
        res['apg'] = apg
        self.req.writejs(ret)
    
    def fn_get_cust_delivery(self):
        ret = {'res':{'len':0, 'apg':[]}}
        cid = self.qsv_int('cid')
        
        pgsz = self.qsv_int('pagesize')
        sidx = self.qsv_int('sidx')
        eidx = self.qsv_int('eidx')
        if pgsz > 100 or eidx - sidx > 5: self.req.exitjs(ret)
        
        cur = self.cur()
        apg = []
        perm = self.user_lvl & (1 << config.USER_PERM_BIT['item stat access'])
        if pgsz > 0 and sidx >= 0 and sidx < eidx:
            
            users = self.getuserlist()
            users_lku = dict([x[:2] for x in users])
        
            cur.execute('select SQL_CALC_FOUND_ROWS sr.num,r.driver_id,r.delivered,r.problem_flag,r.d_id,d.name,d.user_id,sr.order_date,d.ts,sr.sid,sr.sid_type from sync_receipts sr left join deliveryv2_receipt r on (sr.num=r.num) left join deliveryv2 d on (r.d_id=d.d_id) where sr.cid=%s and (sr.type&0xff00)<0x0200 and d.d_id is not null order by sr.num desc, r.d_id desc limit %d,%d' % (
                cid, sidx * pgsz, (eidx - sidx) * pgsz
                )
            )
            for r in cur.fetchall():
                r = list(r)
                r[1] = r[1] and users_lku.get(r[1], 'UNK') or ''
                r[2] = r[2] and 'Y' or 'N'
                r[3] = r[3] and 'Y' or 'N'
                r[6] = r[6] and users_lku.get(r[6], 'UNK') or ''
                r[7] = time.strftime("%m/%d/%y", time.localtime(r[7]))
                r[8] = time.strftime("%m/%d/%y", time.localtime(r[8]))
                r[9] = str(r[9])
                apg.append(r)
        
            cur.execute('select FOUND_ROWS()')
            
        else:
            cur.execute('select count(*) from sync_receipts sr left join deliveryv2_receipt r on (sr.num=r.num) left join deliveryv2 d on (r.d_id=d.d_id) where sr.cid=%s and (sr.type&0xff00)<0x0200 and d.d_id is not null' % (
                cid,
                )
            )
            
        rlen = int(cur.fetchall()[0][0])
        res = ret['res']
        res['len'] = rlen
        res['apg'] = apg
        self.req.writejs(ret)
    
    def fn_get_cust_note(self):
        note_id = self.req.psv_int('note_id')
        if not note_id: return
        
        cur = self.cur()
        cur.execute('select val from customer_comment where id=%s', (note_id,))
        rows = cur.fetchall()
        if not rows: return
        
        self.req.writejs( {'note_id': note_id, 'val': rows[0][0]} )
    
    def fn_del_cust_comment(self):
        cid = self.req.psv_int('cid')
        note_id = self.req.psv_int('note_id')
        if not cid or not note_id: return
        
        cur = self.cur()
        cur.execute('update customer_comment set flag=flag|1 where id=%s and cid=%s', (note_id, cid))
    
        self.req.writejs({'ret':1})
    
    def fn_add_cust_comment(self):
        cid = self.req.psv_int('cid')
        comment = self.req.psv_ustr('comment')[:256].strip()
        if not cid or not comment: return
        note_id = self.req.psv_int('note_id')

        db = self.db()
        cur = db.cur()
        
        cur.execute('select count(*) from sync_customers where sid=%s', (cid,))
        if cur.fetchall()[0][0] <= 0: return
        
        if note_id:
            cur.execute('update customer_comment set val=%s where id=%s and cid=%s', (comment, note_id, cid))
            mid = note_id
        else:
            cur.execute('insert into customer_comment values (null,%s,0,%s,%s,%s)', (
                cid, int(time.time()), self.user_name, comment
                )
            )
            mid = cur.lastrowid
        
        self.req.writejs({'ret':mid})
        
    def fn_get_cust_comment(self):
        ret = {'res':{'len':0, 'apg':[]}}
        cid = self.qsv_int('cid')
        sql_flag = ''
        if not self.qsv_int('flag'): sql_flag = '(flag & 1)=0 and '
        
        pgsz = self.qsv_int('pagesize')
        sidx = self.qsv_int('sidx')
        eidx = self.qsv_int('eidx')
        if pgsz > 100 or eidx - sidx > 5: self.req.exitjs(ret)
        
        cur = self.cur()
        apg = []
        if pgsz > 0 and sidx >= 0 and sidx < eidx:
            cur.execute('select SQL_CALC_FOUND_ROWS ts,name,val,flag,id from customer_comment where '+sql_flag+'cid=%d order by id desc limit %d,%d' % (
                cid, sidx * pgsz, (eidx - sidx) * pgsz
                )
            )
            for r in cur.fetchall():
                r = list(r)
                r[0] = time.strftime("%m/%d/%Y %I:%M:%S %p", time.localtime(r[0]))
                r[3] = (r[3] & 1) and 'Y' or ''
                apg.append(r)
        
            cur.execute('select FOUND_ROWS()')
            
        else:
            cur.execute('select count(*) from customer_comment where '+sql_flag+'cid=%s', (cid,))
            
        rlen = int(cur.fetchall()[0][0])
        res = ret['res']
        res['len'] = rlen
        res['apg'] = apg
        self.req.writejs(ret) 
    
    def fn_get_item_custs(self):
        ret = {'res':{'len':0, 'apg':[]}}
        tid = self.qsv_int('tid')
        
        pgsz = self.qsv_int('pagesize')
        sidx = self.qsv_int('sidx')
        eidx = self.qsv_int('eidx')
        if pgsz > 100 or eidx - sidx > 5: self.req.exitjs(ret)
        
        cur = self.cur()
        apg = []
        perm = self.user_lvl & (1 << config.USER_PERM_BIT['item stat access'])
        if pgsz > 0 and sidx >= 0 and sidx < eidx:
            cur.execute('select SQL_CALC_FOUND_ROWS c.name,sum(h.qtydiff) as total_qty,max(h.docdate) as last_docdate,r.cid from sync_items_hist h left join sync_receipts r on (r.sid=h.docsid and r.sid_type=h.sid_type and (h.flag>>8)<2) left join sync_receipts_customers c on (c.sid=r.cid) where h.itemsid=%d and r.cid is not null group by r.cid order by total_qty asc,r.cid asc limit %d,%d' % (
                tid, sidx * pgsz, (eidx - sidx) * pgsz
                )
            )
            for r in cur.fetchall():
                r = list(r)
                r[2] = time.strftime("%m/%d/%Y %I:%M:%S %p", time.localtime(r[2])),
                r[3] = str(r[3])
                r[1] = round(r[1], 1)
                if not perm: r[1] = 0
                apg.append(r)
        
            cur.execute('select FOUND_ROWS()')
        else:
            cur.execute('select count(*) from sync_items_hist h left join sync_receipts r on (r.sid=h.docsid and r.sid_type=h.sid_type and (h.flag>>8)<2) where h.itemsid=%d and r.cid is not null group by r.cid' % (
                tid,
                )
            )
            
        rlen = int(cur.fetchall()[0][0])
        res = ret['res']
        res['len'] = rlen
        res['apg'] = apg
        self.req.writejs(ret)
    
    
    #specific_vends = {}
    interval__month_mul = [1, 12, 3]
    def fn_get_item_sold_report(self):
        tid = self.qsv_int('tid')
        frm_ts = self.qsv_int('frm_ts')
        to_ts = self.qsv_int('to_ts')
        interval = self.qsv_int('interval')
        if not frm_ts or not to_ts or interval < 0 or interval >= len(self.interval__month_mul): return
        imm = self.interval__month_mul[interval]
        
        lt = time.localtime(frm_ts)
        year,month = tools.get_date_lower(lt.tm_year, lt.tm_mon, imm)
        frm_ts = int(time.mktime(datetime.date(int(year), int(month), 1).timetuple()))
        
        lt = time.localtime(to_ts)
        year,month = tools.get_date_upper(lt.tm_year, lt.tm_mon, imm)
        to_ts = int(time.mktime(datetime.date(int(year), int(month), 1).timetuple()))
        
        cur = self.cur()
        
        """
        sv = self.specific_vends.get(self.user_name.lower())
        if sv != None:
            cur.execute('select detail from sync_items where sid=%d' % tid)
            row = cur.fetchall()
            if not row: return
            detail = json.loads(row[0][0])
            allowed = None
            for vend in detail['vends']:
                allowed = sv.get(vend[0].lower())
                if allowed == None: continue
                if not allowed: return
                break
            if allowed == None and not sv.get(0, False): return
        """
        
        cur.execute('select r.sid,r.sid_type,r.type,r.order_date,h.qtydiff from sync_items_hist h left join sync_receipts r on (h.docsid=r.sid and h.sid_type=r.sid_type) where h.itemsid=%d and r.order_date>=%d and r.order_date<%d and (h.flag>>8)<=1' % (
            tid, frm_ts, to_ts
            )
        )
        stat = {}
        for r in cur.fetchall():
            lt = time.localtime(int(r[3]))
            year,month = tools.get_date_lower(lt.tm_year, lt.tm_mon, imm)
            
            k = '%04d-%02d' % (year, month)
            s = stat.get(k)
            if not s: s = stat[k] = {'qty': [0, 0], 'count':[0, 0]}
            
            sid_type = int(r[1])
            s['qty'][sid_type] += -float(r[4])
            s['count'][sid_type] += 1
            
        stat = stat.items()
        stat.sort(key=lambda x: x[0])
        
        self.req.writejs({'tid':str(tid), 'stat':stat})
    
    fn_get_item_sold_report.PERM = 1 << config.USER_PERM_BIT['item stat access']
    
    TENDER_TYPES = ('None', 'Cash', 'Check', 'Credit', 'Debit', 'UNK', 'Account', '', 'Deposit', 'Split')
    PRICE_LEVELS = ['Regular Price', 'Wholesale 1', 'Wholesale 2', 'special', 'Dealer Price']
    def fn_printreceipt(self):
        rid = self.qsv_int('rid', None)
        if rid == None: return
        
        db = self.db()
        cur = db.cur()
        db_col_nzs = ('r_sid', 'r_sid_type', 'r_rid', 'r_cid', 'r_so_sid', 'r_so_type', 'r_flag', 'r_num', 'r_assoc', 'r_cashier', 'r_price_level', 'r_order_date', 'r_creation_date', 'r_global', 'r_items')
        cur.execute('select * from sync_receipts where sid=%d and sid_type=0' % (rid,))
        r = cur.fetchall()
        if not r: return
        r = dict(zip(db_col_nzs, r[0]))
        
        r['r_flag'] = int(r['r_flag'])
        r['r_order_date'] = time.strftime("%m/%d/%Y %I:%M:%S %p", time.localtime(int(r['r_order_date'])))
        r['r_creation_date'] = time.strftime("%m/%d/%Y %I:%M:%S %p", time.localtime(int(r['r_creation_date'])))
        
        r['r_global'] = json.loads(r['r_global'])
        r['r_items'] = json.loads(r['r_items'])
        
        r['auto_print'] = self.qsv_int('auto_print')
        
        r['price_lvls'] = self.PRICE_LEVELS
        r['tender_types'] = self.TENDER_TYPES
        
        r['round_ex'] = config.round_ex
        
        r['comment'] = comment = []
        cur.execute('select ts,name,flag,comment from receipt_comment where sid=%s and sid_type=0 order by rc_id asc', (r['r_sid'],))
        for x in cur.fetchall():
            comment.append((
                time.strftime("%m/%d/%y %I:%M:%S %p", time.localtime(x[0])),
                x[1],
                x[2],
                x[3]
            ))
        
        cur.execute('select r.*,d.name,d.ts from deliveryv2_receipt r left join deliveryv2 d on (r.d_id=d.d_id) where r.num=%s order by r.d_id desc', (r['r_num'],))
        nzs = cur.column_names
        r['delivery_info'] = delivery_info = []
        for x in cur.fetchall():
            x = dict(zip(nzs, x))
            x['ts'] = time.strftime("%m/%d/%y", time.localtime(x['ts']))
            x['js'] = json.loads(x['js'])
            delivery_info.append(x)
        r['users_lku'] = dict([ x[:2] for x in self.getuserlist() ])
        r['PROBLEMS'] = Delivery.PROBLEMS
        
        self.req.writefile('receipt_print_v2.html', r)
        
    
    def fn_addcomment(self):
        rid = self.req.psv_int('rid')
        if not rid: return
        
        comment = self.req.psv_ustr('comment')[:256].strip()
        if not comment: return
        
        db = self.db()
        cur = db.cur()
        
        cur.execute('select count(*) from sync_receipts where sid=%s and sid_type=0', (rid,))
        if cur.fetchall()[0][0] <= 0: return
        
        cur.execute('insert into receipt_comment values (null,%s,0,%s,0,%s,%s)', (
            rid, int(time.time()), self.user_name, comment
            )
        )
        
        self.req.writejs({'order_id':rid})
    
    regx_kw = re.compile(u'[^ 0-9a-z,]+', re.I|re.M|re.S)
    def fn_srchcust(self):
        kw = self.qsv_str('term')
        if not kw: return
        mode = self.qsv_int('mode')
        
        kws = set(self.regx_kw.sub(u' ', kw).strip().lower().replace(u',', u' ').strip().split(u' '))
        kws.discard(u'')
        if not kws: return
        
        db = self.db()
        cur = db.cur()
        if mode:
            kw = '+' + u' +'.join([k for k in kws])
        else:
            kw = '+' + u' +'.join([k + '* ' + k for k in kws])
        qs = "select sid,name,detail,(match(name,lookup) against (%s in boolean mode) + match(name) against (%s in boolean mode)*2) as pos from sync_receipts_customers where match(name,lookup) against (%s in boolean mode) order by pos desc,sid desc limit 10"
        cur.execute(qs, (kw, kw.replace(u'+', u''), kw))
        res = [ [str(x[0]),] + list(x[1:]) for x in cur.fetchall()]
        
        self.req.writejs(res)

    def fn_srchitem(self):
        kw = self.qsv_str('term')
        if not kw: return
        mode = self.qsv_int('mode')
        
        kws = set(self.regx_kw.sub(u' ', kw).strip().lower().replace(u',', u' ').strip().split(u' '))
        kws.discard(u'')
        if not kws: return
        
        db = self.db()
        cur = db.cur()
        if mode:
            kw = '+' + u' +'.join([k for k in kws])
        else:
            kw = '+' + u' +'.join([k + '* ' + k for k in kws])
        qs = "select sid,num,name,detail,(match(lookup,name) against (%s in boolean mode) + match(lookup) against (%s in boolean mode)*2) as pos from sync_receipts_items where match(lookup,name) against (%s in boolean mode) order by pos desc,num asc limit 10"
        cur.execute(qs, (kw, kw.replace(u'+', u''), kw))
        res = [ [str(x[0]),] + list(x[1:]) for x in cur.fetchall()]
        
        self.req.writejs(res)
    
    ORDER_TYPE = ('Sales', 'Return', 'Deposit', 'Refund')
    def fn_getpagecust(self):
        cid = self.qsv_int('cid', None)
        if cid == None: return
        pgsz = self.qsv_int('pagesize')
        sidx = self.qsv_int('sidx')
        eidx = self.qsv_int('eidx')
        
        if pgsz > 100 or eidx - sidx > 5: return
        
        db = self.db()
        cur = db.cur()
        rpg = {}
        if pgsz > 0 and sidx >= 0 and sidx < eidx:
            cur.execute('select sid,type,num,assoc,cashier,order_date,global_js,sid_type,so_sid from sync_receipts where cid=%d order by creation_date desc, sid desc, sid_type desc limit %d,%d' % (
                cid,
                sidx * pgsz, (eidx - sidx) * pgsz
                )
            )
            d = cur.fetchall()
            
            for i in range(sidx, eidx): rpg[i] = []
            if d:
                k = 0
                for r in d:
                    flag = int(r[1])
                    r_tender_type = (flag >> 16) & 0xFF
                    r_type = (flag >> 8) & 0xFF
                    r_status = (flag >> 0) & 0xFF
                    r_global = json.loads(r[6])
                    
                    if r_type >= 0 and r_type < len(self.ORDER_TYPE):
                        t_type = self.ORDER_TYPE[ r_type ]
                    else:
                        t_type = 'UNK' + str(r_type)
                    if r_status: t_type += ' (R)'
                    t_assoc = r[3]
                    if r[3] != r[4]: t_assoc += ' (' + r[4] + ')'
                    
                    r = (
                        r[2],
                        t_type,
                        r_global.get('sonum') or '',
                        t_assoc,
                        "$%0.2f" % config.round_ex(r_global['total']),
                        time.strftime("%m/%d/%Y %I:%M:%S %p", time.localtime(int(r[5]))),
                        str(r[0]),
                        int(r[7]),
                        r[8] and str(r[8]) or ''
                    )
                    rpg[sidx].append(r)
                    k += 1
                    if k == pgsz:
                        sidx += 1
                        k = 0
        
        cur.execute('select count(*) from sync_receipts where cid=%d' % (cid,))
        rlen = int(cur.fetchall()[0][0])
        
        self.req.writejs( {'res':{'len':rlen, 'rpg':rpg}} )

    ITEM_HIST_TYPE = ('Sales', 'Return', 'Receive Items', 'Return to Vendor', 'Adjustment', 'Cost Adjustment')
    def fn_getpageitem(self):
        tid = self.qsv_int('tid', None)
        if tid == None: return
        pgsz = self.qsv_int('pagesize')
        sidx = self.qsv_int('sidx')
        eidx = self.qsv_int('eidx')
        
        if pgsz > 100 or eidx - sidx > 5: return
        
        db = self.db()
        cur = db.cur()
        rpg = {}
        if pgsz > 0 and sidx >= 0 and sidx < eidx:
            cur.execute('select docsid,docnum,( if((h.flag>>8)>1, h.flag, (select r.type from sync_receipts r where r.sid=h.docsid and r.sid_type=h.sid_type limit 1)) ) as flag,doctxt,qtydiff,docdate,sid_type,sid from sync_items_hist h where itemsid=%d order by docdate desc,sid desc limit %d,%d' % (
                tid,
                sidx * pgsz, (eidx - sidx) * pgsz
                )
            )
            d = cur.fetchall()
            
            for i in range(sidx, eidx): rpg[i] = []
            if d:
                k = 0
                for r in d:
                    flag = int(r[2])
                    r_type = (flag >> 8) & 0xFF
                    r_status = (flag >> 0) & 0xFF
                    
                    if r_type >= 0 and r_type < len(self.ITEM_HIST_TYPE):
                        t_type = self.ITEM_HIST_TYPE[ r_type ]
                    else:
                        t_type = 'UNK' + str(r_type)
                    if r_status: t_type += ' (R)'
                    
                    r = (
                        r[1],
                        t_type,
                        r[3],
                        float(r[4]),
                        time.strftime("%m/%d/%Y %I:%M:%S %p", time.localtime(int(r[5]))),
                        str(r[0]),
                        r_type,
                        int(r[6]),
                        str(r[7])
                    )
                    rpg[sidx].append(r)
                    k += 1
                    if k == pgsz:
                        sidx += 1
                        k = 0
        
        cur.execute('select count(*) from sync_items_hist where itemsid=%d' % (tid,))
        rlen = int(cur.fetchall()[0][0])
        
        self.req.writejs( {'res':{'len':rlen, 'rpg':rpg}} )
        
    def fn_hasreceipt(self):
        rno = self.qsv_int('rno')
        
        db = self.db()
        cur = db.cur()
        cur.execute('select sid,sid_type from sync_receipts where num=%d limit 1' % (rno,))
        res = cur.fetchall()
        if not res: return
        res = res[0]
        
        self.req.writejs( {'rno': rno, 'sid': str(res[0]), 'sid_type': int(res[1])} )
        
    def fn_custhist(self):
        cid = self.qsv_int('cid', None)
        if cid == None: return
        
        dg_type = self.qsv_int('dg_type')
        
        db = self.db()
        cur = db.cur()
        cur.execute('select sid,name,detail from sync_customers where sid=%d limit 1' % (cid,))
        res = cur.fetchall()
        if not res: return
        
        res = res[0]
        cust = {'cust_sid': res[0], 'cust_name': res[1], 'cust_info': json.loads(res[2]), 'dg_type': dg_type}
        
        self.req.writefile('hist_cust.html', cust)
    
    def fn_itemhist(self):
        tid = self.qsv_int('tid', None)
        if tid == None: return
        
        dg_type = self.qsv_int('dg_type')
        
        db = self.db()
        cur = db.cur()
        cur.execute('select s.sid,s.num,s.name,s.detail,i.imgs,s.deptsid,s.status from sync_items s left join item i on (s.sid=i.sid) where s.sid=%d limit 1' % (tid,))
        res = cur.fetchall()
        if not res: return
        
        res = res[0]
        
        l_depts = cPickle.loads(self.getconfigv2('departments'))
        d_r_depts = dict([(f_b, f_a) for f_a,f_b in l_depts])
        d_r_status = dict([(f_b, f_a) for f_a,f_b in const.ITEM_L_STATUS])
        dept = d_r_depts.get(res[5])
        cate = const.ITEM_D_DEPT.get(dept)
        
        item = {
            'item_sid': res[0],
            'item_num': res[1],
            'item_name': res[2],
            'item_info': json.loads(res[3]),
            'dg_type': dg_type,
            'item_imgs': res[4] and res[4].split('|') or [],
            'item_status': d_r_status.get(res[6]),
            'item_dept': dept,
            'item_cate': cate,
        }
        
        self.req.writefile('hist_item.html', item)


    def fn_get_custid_by_histid(self):
        sid = self.req.qsv_int('sid')
        sid_type = self.req.qsv_int('sid_type')
        
        cur = self.cur()
        cur.execute('select flag,docsid,sid_type from sync_items_hist where sid=%s and sid_type=%s', (sid, sid_type))
        rows = cur.fetchall()
        if not rows: return
        flag, sid, sid_type = rows[0]
        
        r_type = (flag >> 8) & 0xFF
        if r_type >= 2: return
        
        cur.execute('select cid from sync_receipts where sid=%s and sid_type=%s', (sid, sid_type))
        rows = cur.fetchall()
        if not rows: return
        
        self.req.writejs( {'cid': str(rows[0][0])} )
        
