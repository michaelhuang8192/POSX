import sys
import os
import glob
import json
import config
import cPickle
import const
import time
import datetime
import bisect

DEFAULT_PERM = 1 << config.USER_PERM_BIT['admin']
class RequestHandler(App.load('/advancehandler').RequestHandler):

    def fn_default(self):
        self.req.writefile('report_cnt.html')

    def fn_get_customer_sale(self):
        cid = self.req.qsv_int('cid')
        rjs = (self.get_data_file_cached('receipt_report', 'receipt_report.txt') or {}).get('customer', {})
        ms = rjs.get(cid) or []
        
        lst = []
        for mts,msa in ms: lst.append( (time.strftime("%Y-%m", time.localtime(mts)), '%0.2f' % (msa[0],)) )
        lst.reverse()
        
        self.req.writejs(lst)

    def fn_year_to_year(self):
        yrs = {}
        rjs = (self.get_data_file_cached('receipt_report', 'receipt_report.txt') or {}).get('summary', [])
        for r in rjs:
            yrs.setdefault(time.localtime(r[0]).tm_year, [0])[0] += r[1][1]
        yrs = yrs.items()
        yrs.sort(key=lambda f_x: f_x[0])
        dps = []
        for yr,amt in yrs:
            dps.append({'label': yr, 'y': round(amt[0], 2)})
        
        cfg = {
            'zoomEnabled': True,
            'theme': "theme2",
            'title': {'text': "Year To Year"},
            'axisY': {'title':"Total Sale $"},
            'data': [
                {'type': "column", 'dataPoints': dps},
            ]
        }
        
        self.req.writefile('report/year_to_year.html', {'chart_cfg': json.dumps(cfg, separators=(',',':'))})

    def fn_transaction(self):
        
        self.req.writefile('report/transaction.html')
        
    def fn_cust_by_dept(self):
        r = {
            'const': const
        }
        self.req.writefile('cust_by_dept.html', r)
    
    def fn_get(self):
        ret = {'res':{'len':0, 'apg':[]}}

        pgsz = self.qsv_int('pagesize')
        sidx = self.qsv_int('sidx')
        eidx = self.qsv_int('eidx')
        if pgsz > 100 or eidx - sidx > 5: self.req.exitjs(ret)
        
        frm_ts = to_ts = 0
        dt = self.qsv_str('frm')
        if dt: frm_ts = int(time.mktime(time.strptime(dt, "%Y-%m")))
        dt = self.qsv_str('to')
        if dt: to_ts = int(time.mktime(time.strptime(dt, "%Y-%m")))
        if frm_ts > to_ts: self.req.exitjs(ret)
        
        rjs = (self.get_data_file_cached('receipt_report', 'receipt_report.txt') or {}).get('customer', {})
        
        cur = self.cur()
        apg = []
        if pgsz > 0 and sidx >= 0 and sidx < eidx:
            cur.execute('select SQL_CALC_FOUND_ROWS sid,name,detail from sync_customers order by sid desc limit %d,%d' % (
                sidx * pgsz, (eidx - sidx) * pgsz
                )
            )
            nzs = cur.column_names
            for r in cur:
                sid,name,detail = r
                gjs = json.loads(detail)
                addr = []
                addr.append(gjs['address1'] + (gjs['address2'] and ' ' + gjs['address2'] or ''))
                addr.append(gjs['city'])
                addr.append(gjs['state'] + (gjs['zip'] and ' ' + gjs['zip'] or ''))
                phone = gjs['phone1']
                
                ldt = rjs.get(sid, [])
                ldt_k = [ f_x[0] for f_x in ldt ]
                ttl_sales = 0
                for dt in ldt[bisect.bisect_left(ldt_k, frm_ts):bisect.bisect_right(ldt_k, to_ts)]:
                    ttl_sales += dt[1][0]
                    
                r = (
                    name,
                    ','.join([f_a for f_a in addr if f_a]),
                    phone,
                    ttl_sales and '%0.2f' % (ttl_sales, ) or '',
                    str(sid)
                )
                apg.append(r)
        
            cur.execute('select FOUND_ROWS()')
            
        else:
            cur.execute('select count(*) from sync_customers')
            
        rlen = int(cur.fetchall()[0][0])
        res = ret['res']
        res['len'] = rlen
        res['apg'] = apg
        self.req.writejs(ret)
        
        
        