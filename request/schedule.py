import json
import time
import config
import datetime
import base64
import const

ZONES = const.ZONES
MAX_DAYS = 7
WDAYS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']

SALES_PERM = 1 << config.USER_PERM_BIT['sales']
DELIVERY_MGR_PERM = 1 << config.USER_PERM_BIT['delivery_mgr']


REC_FLAG_ACCEPTED = 1 << 0
REC_FLAG_RESCHEDULED = 1 << 1
REC_FLAG_CANCELLING = 1 << 2
REC_FLAG_CHANGED = 1 << 3

CFG_SCHEDULE_UPDATE_SEQ = config.CFG_SCHEDULE_UPDATE_SEQ


ORD_TYPE=('Sales', 'Return', 'Deposit', 'Refund', 'Payout', 'Payin')


DEFAULT_PERM = 0x00000001
class RequestHandler(App.load('/basehandler').RequestHandler):
    
    def fn_default(self):
        r = {
            'sales': [ f_user for f_user in self.getuserlist() if f_user[2] & SALES_PERM ],
            'zones': [ f_x[0] for f_x in ZONES ],
            'has_perm_delivery_mgr': DELIVERY_MGR_PERM,
            'REC_FLAG_CANCELLING': REC_FLAG_CANCELLING,
            'REC_FLAG_ACCEPTED': REC_FLAG_ACCEPTED,
            'REC_FLAG_RESCHEDULED': REC_FLAG_RESCHEDULED,
            'REC_FLAG_CHANGED': REC_FLAG_CHANGED,
            'CFG_SCHEDULE_UPDATE_SEQ': CFG_SCHEDULE_UPDATE_SEQ,
            'sc_upd_seq': self.getconfig(CFG_SCHEDULE_UPDATE_SEQ)
        }
        self.req.writefile('schedule.html', r)
    
    def inc_seq(self):
        self.cur().execute('update config set cval=cval+1 where cid=%s', (CFG_SCHEDULE_UPDATE_SEQ,))
    
    def add_notes(self, lst):
        self.cur().executemany('insert into doc_note values(null,'+str(int(time.time()))+',%s,%s,0,'+str(self.user_id)+',%s)', lst)
    
    def fn_del_rec(self):
        d_date = datetime.date.today()
        d_date = d_date.year * 10000 + d_date.month * 100 + d_date.day
        sc_id = self.req.psv_int('sc_id')
        
        cur = self.cur();
        cur.execute('select * from schedule where sc_id=%s and sc_date>=%s', (sc_id, d_date))
        rows = cur.fetchall()
        if not rows: return
        row = dict(zip(cur.column_names, rows[0]))
        
        if row['sc_flag'] & REC_FLAG_CANCELLING:
            self.req.exitjs({'err': -11, 'err_s': 'Cancellation is pending'})
        
        if row['sc_flag'] & REC_FLAG_ACCEPTED:
            cur.execute('update schedule set sc_flag=sc_flag|%s where sc_id=%s and sc_rev=%s and sc_flag&%s!=0', (
                REC_FLAG_CANCELLING, sc_id, row['sc_rev'], REC_FLAG_ACCEPTED
                )
            )
        else:
            cur.execute('delete from schedule where sc_id=%s and sc_rev=%s and sc_flag&%s=0', (
                sc_id, row['sc_rev'], REC_FLAG_ACCEPTED
                )
            )
            
        err = int(cur.rowcount <= 0)
        if not err:
            self.inc_seq()
        
        self.req.writejs({'err': err})
    
    def fn_del(self):
        sc_ids = map(int, self.req.psv_ustr('sc_ids').split('|'))
        docs = self.get_docs_by_sc_ids(sc_ids)
        #if len(sc_ids) != len(docs): self.req.exitjs({'err': -2, 'err_s': "size not matched"})
        
        cur = self.cur()
        c = 0
        for r in docs:
            crc = json.loads(r['doc'][2]).get('crc', 0)
            cur.execute('delete from schedule where sc_id=%s and sc_flag&%s!=0', (
                r['sc_id'], REC_FLAG_CANCELLING
            ))
            if cur.rowcount > 0: c += 1
    
        if c: self.inc_seq()
        i_warning_s = None
        if len(sc_ids) != c: i_warning_s = '%d out of %d processed' % (c, len(sc_ids))
        
        self.req.writejs({'err': 0, 'i_warning_s': i_warning_s})
    fn_del.PERM = DELIVERY_MGR_PERM
    
    
    def fn_get_doc(self):
        d_num = self.req.qsv_ustr('num')
        if not d_num.isdigit(): return
        d_type = int(bool(self.req.qsv_int('type')))
        
        cur = self.cur()
        if d_type:
            cur.execute('select sid,num,assoc,order_date,global_js from sync_receipts where num=%s and sid_type=0 and (type&0xFF)=0 order by sid desc limit 1', (
                int(d_num),
                )
            )
        else:
            cur.execute('select sid,sonum,clerk,sodate,global_js from sync_salesorders where sonum=%s and (status>>4)=0 order by sid desc limit 1', (
                d_num,
                )
            )
        
        row = cur.fetchall()
        if not row: self.req.exitjs({'err': -1, 'err_s': 'document #%s not found' % (d_num,)})
        sid,num,assoc,doc_date,gjs = row[0]
        
        gjs = json.loads(gjs)
        company = (gjs.get('customer') or {}).get('company') or ''
        
        loc = None
        if gjs['shipping']:
            loc = gjs['shipping'].get('loc')
        elif gjs['customer']:
            loc = gjs['customer'].get('loc')
        
        zidx = 0
        if loc != None:
            cur.execute('select zone_id from address where loc=%s and flag!=0', (base64.b64decode(loc),))
            rr = cur.fetchall()
            if rr: zidx = rr[0][0]
            
        recs = []
        js = {
            'type': d_type,
            'num': num,
            'sid':str(sid),
            'assoc': assoc,
            'company': company,
            'total': gjs['total'],
            'recs': recs,
            'doc_date': time.strftime("%m/%d/%Y", time.localtime(doc_date)),
            'zone_nz': ZONES[zidx][0]
        }
        
        cur.execute('select sc_id,sc_date,sc_rev,sc_flag,sc_prio,sc_note from schedule where doc_type=%s and doc_sid=%s order by sc_id asc', (
            d_type, sid
            )
        )
        nzs = cur.column_names
        for r in cur.fetchall():
            r = dict(zip(nzs, r))
            recs.append(r)
        
        self.req.writejs(js)
    
    def fn_set_doc(self):
        d_sid = self.req.psv_int('sid')
        
        d_date = map(int, self.req.psv_ustr('date').split('/'))
        o_date = datetime.date(d_date[2], d_date[0], d_date[1])
        if o_date < datetime.date.today(): self.req.exitjs({'err': -9, 'err_s': "Invalid Date"})
        d_date = o_date.year * 10000 + o_date.month * 100 + o_date.day
        
        d_type = int(bool(self.req.psv_int('type')))
        rev = self.req.psv_int('rev')
        prio = min(max(-1, self.req.psv_int('prio')), 2)
        sc_id = self.req.psv_int('sc_id')
        note = self.req.psv_ustr('note')[:256].strip()
        
        cts = int(time.time())
        
        cur = self.cur()
        if d_type:
            cur.execute('select num from sync_receipts where sid=%s and sid_type=0 and (type&0xFF)=0', (
                d_sid,
                )
            )
        else:
            cur.execute('select sonum from sync_salesorders where sid=%s and (status>>4)=0', (
                d_sid,
                )
            )
        
        row = cur.fetchall()
        if not row: return
        d_num = row[0][0]
        
        d_note = None
        if sc_id == 0:
            cur.execute('insert into schedule values(null,%s,1,%s,%s,%s,%s,0,%s)', (
                d_date, 0, prio, d_type, d_sid, note
                )
            )
            sc_id = cur.lastrowid
            d_note = 'Schedule Delivery Date - %s' % (o_date.strftime('%m/%d/%y'), )
        else:
            cur.execute("select sc_flag,sc_date,sc_prio,sc_note from schedule where sc_id=%s and sc_rev=%s", (
                sc_id, rev
                )
            )
            row = cur.fetchall()
            if not row: self.req.exitjs({'err': -3, 'err_s': "document #%s - record #%s - can't find the record" % (d_num, sc_id)})
            old_sc_flag,old_sc_date,old_sc_prio,old_sc_note = row[0]
            if old_sc_date == d_date and old_sc_prio == prio and old_sc_note == note: self.req.exitjs({'err': -2, 'err_s': "document #%s - record #%s - nothing changed" % (d_num, sc_id)})
            
            if old_sc_flag & REC_FLAG_ACCEPTED and not(self.user_lvl & DELIVERY_MGR_PERM): self.req.exitjs({'err': -2, 'err_s': "can't change"})
            cur.execute("update schedule set sc_rev=sc_rev+1,sc_flag=sc_flag|%s,sc_date=%s,sc_prio=%s,sc_note=%s where sc_id=%s and sc_rev=%s", (
                old_sc_date != d_date and REC_FLAG_RESCHEDULED or 0, d_date, prio, note, sc_id, rev
                )
            )
            if old_sc_date != d_date:
                m,d = divmod(old_sc_date, 100)
                y,m = divmod(m, 100)
                o_old_date = datetime.date(y, m, d)
                d_note = 'Reschedule Delivery Date From %s To %s' % (o_old_date.strftime('%m/%d/%y'), o_date.strftime('%m/%d/%y'), )
            
        err = int(cur.rowcount <= 0)
        if err:
            self.req.exitjs({'err': -2, 'err_s': "document #%s - can't make any update" % (d_num, )})
        else:
            self.inc_seq()
            if d_note: self.add_notes(([d_type, d_sid, d_note],))
        
        self.req.exitjs({'err': err, 'sc_id': sc_id})
    
    def get_docs_by_sc_ids(self, sc_ids, full=False):
        if not sc_ids: return []
        sc_ids = sc_ids[:100]
        return self._get_docs_by_sc_ids(sc_ids, full)
        
    def _get_docs_by_sc_ids(self, sc_ids, full=False):
        so_sids = set()
        rc_sids = set()
        sc_lst = []
        
        cur = self.cur()
        cur.execute('select ' + (full and '*' or 'sc_id,doc_type,doc_sid') + ' from schedule where sc_id in (%s)' % (','.join(map(str,sc_ids)),))
        nzs = cur.column_names
        for r in cur.fetchall():
            r = dict(zip(nzs, r))
            sc_lst.append(r)
            if r['doc_type']:
                rc_sids.add(r['doc_sid'])
            else:
                so_sids.add(r['doc_sid'])
                
        d_so = {}
        if so_sids:
            cur.execute('select ' + (full and 'sid,cust_sid,status,sonum,clerk,cashier,sodate,global_js,items_js' or 'sid,sonum,global_js') + ' from sync_salesorders where sid in (%s)' % (','.join(map(str, so_sids)), ))
            for r in cur.fetchall(): d_so[r[0]] = r
            
        d_rc = {}
        if rc_sids:
            cur.execute('select ' + (full and 'sid,cid,type,num,assoc,cashier,order_date,global_js,items_js' or 'sid,num,global_js') + ' from sync_receipts where sid_type=0 and sid in (%s)' % (','.join(map(str, rc_sids)), ))
            for r in cur.fetchall(): d_rc[r[0]] = r
        
        _sc_lst = []
        for r in sc_lst:
            if r['doc_type']:
                doc = d_rc.get(r['doc_sid'])
            else:
                doc = d_so.get(r['doc_sid'])
            if not doc: continue
            
            r['doc'] = doc
            _sc_lst.append(r)
        
        return _sc_lst
    
    def fn_update_crc(self):
        sc_ids = map(int, self.req.psv_ustr('sc_ids').split('|'))
        docs = self.get_docs_by_sc_ids(sc_ids)
        #if len(sc_ids) != len(docs): self.req.exitjs({'err': -2, 'err_s': "size not matched"})
        
        cur = self.cur()
        c = 0
        for r in docs:
            crc = json.loads(r['doc'][2]).get('crc', 0)
            cur.execute('update schedule set sc_rev=sc_rev+1,doc_crc=%s where sc_id=%s and sc_flag&%s!=0', (
                crc, r['sc_id'], REC_FLAG_ACCEPTED
            ))
            if cur.rowcount > 0: c += 1
    
        if c: self.inc_seq()
        i_warning_s = None
        if len(sc_ids) != c: i_warning_s = '%d out of %d updated' % (c, len(sc_ids))
        
        self.req.writejs({'err': 0, 'i_warning_s': i_warning_s})
    fn_update_crc.PERM = DELIVERY_MGR_PERM
    
    def fn_accept(self):
        sc_ids = map(int, self.req.psv_ustr('sc_ids').split('|'))
        docs = self.get_docs_by_sc_ids(sc_ids)
        #if len(sc_ids) != len(docs): self.req.exitjs({'err': -2, 'err_s': "size not matched"})
        
        cur = self.cur()
        c = 0
        for r in docs:
            crc = json.loads(r['doc'][2]).get('crc', 0)
            cur.execute('update schedule set sc_flag=sc_flag|%s,sc_rev=sc_rev+1,doc_crc=%s where sc_id=%s and sc_flag&%s=0', (
                REC_FLAG_ACCEPTED, crc, r['sc_id'], REC_FLAG_ACCEPTED
            ))
            if cur.rowcount > 0: c += 1
    
        if c: self.inc_seq()
        i_warning_s = None
        if len(sc_ids) != c: i_warning_s = '%d out of %d updated' % (c, len(sc_ids))
        
        self.req.writejs({'err': 0, 'i_warning_s': i_warning_s})
    fn_accept.PERM = DELIVERY_MGR_PERM
    
    def fn_set_zone_state(self):
        date = self.req.psv_int('date')
        zidx = self.req.psv_int('zidx')
        state = self.req.psv_int('state')
        if zidx < 1 or zidx >= len(ZONES) or state not in (0, -1, 1): return
        
        m,d = divmod(date, 100)
        y,m = divmod(m, 100)
        dto = datetime.date(y, m, d)
        if dto < datetime.date.today(): self.req.exitjs({'err': -9, 'err_s': "Invalid Date"})
        
        cur = self.cur()
        cur.execute('insert into schedule_special values(%s,%s,%s) on duplicate key update ss_val=%s', (
            date, zidx, state, state
            )
        )
        err = int(cur.rowcount <= 0)
        if not err:
            self.inc_seq()
        
        self.req.writejs({'err': err})
    fn_set_zone_state.PERM = DELIVERY_MGR_PERM
    
    def fn_get_overview(self):
        clerk_id = self.qsv_int('clerk_id')
        
        odt = datetime.date.today()
        cdt = odt.year * 10000 + odt.month * 100 + odt.day
        
        d_ss = {}
        cur = self.cur()
        cur.execute('select ss_date,ss_zidx,ss_val from schedule_special where ss_date>=%s', (cdt,))
        for r in cur.fetchall(): d_ss[ (r[0] << 26) | r[1] ] = r[2]
        
        d_dt = {}
        for r in self.get_docs(cdt, -1, clerk_id, 1):
            zid = r['zone_id']
            d = d_dt.setdefault(r['sc_date'], [None,] * len(ZONES))
            if not d[zid]: d[zid] = [0, 0, 0, 0, 0]
            d = d[zid]
            
            if r['sc_flag'] & REC_FLAG_ACCEPTED:
                d[1] += 1
            else:
                d[0] += 1
            
            if r['sc_flag'] & REC_FLAG_RESCHEDULED:
                d[2] += 1
                
            if r['sc_flag'] & REC_FLAG_CANCELLING:
                d[3] += 1
            
            if r['sc_flag'] & REC_FLAG_CHANGED:
                d[4] += 1
        
        l_dt = d_dt.items()
        l_dt.sort(key=lambda f_x: f_x[0])
        
        dt_1 = datetime.timedelta(1)
        n_dt = []
        sdt = odt
        max_days = MAX_DAYS
        for i in range(len(l_dt)):
            dt,dd = l_dt[i]
            m,d = divmod(dt, 100)
            y,m = divmod(m, 100)
            ndt = datetime.date(y, m, d)
            
            if max_days > 0:
                for j in range((ndt - sdt).days):
                    wd = sdt.weekday()
                    if wd != 6:
                        max_days -= 1
                        n_dt.append( (sdt.strftime("%a (%m/%d)"), None, wd, sdt.year  * 10000 + sdt.month * 100 + sdt.day) )
                        if max_days <= 0: break
                    sdt = sdt + dt_1
            wd = ndt.weekday()
            if wd != 6: max_days -= 1
            n_dt.append( (ndt.strftime("%a (%m/%d)"), dd, wd, ndt.year  * 10000 + ndt.month * 100 + ndt.day) )
            sdt = ndt + dt_1
            
        while max_days > 0:
            wd = sdt.weekday()
            if wd != 6:
                max_days -= 1
                n_dt.append( (sdt.strftime("%a (%m/%d)"), None, wd, sdt.year  * 10000 + sdt.month * 100 + sdt.day) )
            sdt = sdt + dt_1
        
        zones = []
        for j in range(len(ZONES)):
            z,s = ZONES[j]
            f = [0,] * len(n_dt)
            zones.append( (0, f) )
            for i in range(len(n_dt)):
                ss = d_ss.get((n_dt[i][3] << 26) | j)
                if ss != None:
                    f[i] = ss
                elif n_dt[i][2] in s:
                    f[i] = 1
        
        self.req.writejs({'dt': n_dt, 'zones': zones})

    def get_docs(self, date, zone_id, clerk_id, mode=0):
        clerk = None
        if clerk_id:
            clerk = self.finduser(clerk_id)
            if not clerk: return None

        so_sids = set()
        rc_sids = set()
        sc_lst = []
        cur = self.cur()
        if mode:
            where = ' where sc_date>=%s'
        else:
            where = ' where sc_date=%s order by sc_prio desc,sc_id desc'
        cur.execute('select sc_id,sc_date,sc_flag,doc_type,doc_sid,doc_crc from schedule ' + where, (date,))
        nzs = cur.column_names
        for r in cur.fetchall():
            r = dict(zip(nzs, r))
            sc_lst.append(r)
            if r['doc_type']:
                rc_sids.add(r['doc_sid'])
            else:
                so_sids.add(r['doc_sid'])
        
        d_so = {}
        if so_sids:
            sql = 'select sid,sonum,clerk,sodate,global_js from sync_salesorders where sid in (%s)' % (','.join(map(str, so_sids)), )
            if clerk:
                cur.execute(sql + ' and clerk=%s', (clerk[1].lower(),))
            else:
                cur.execute(sql)
            for r in cur.fetchall(): d_so[r[0]] = r
            
        d_rc = {}
        if rc_sids:
            sql = 'select sid,num,assoc,order_date,global_js from sync_receipts where sid_type=0 and sid in (%s)' % (','.join(map(str, rc_sids)), )
            if clerk:
                cur.execute(sql + ' and assoc=%s', (clerk[1].lower(),))
            else:
                cur.execute(sql)
            for r in cur.fetchall(): d_rc[r[0]] = r
        
        locs = set()
        _sc_lst = []
        for r in sc_lst:
            if r['doc_type']:
                doc_data = d_rc.get(r['doc_sid'])
            else:
                doc_data = d_so.get(r['doc_sid'])
            if not doc_data: continue
            _sc_lst.append(r)
            
            r['doc_data'] = doc_data
            doc_js = r['doc_js'] = json.loads(doc_data[4])
            if doc_js['shipping']:
                doc_loc = doc_js['shipping'].get('loc')
            elif doc_js['customer']:
                doc_loc = doc_js['customer'].get('loc')
            
            r['doc_loc'] = doc_loc
            if doc_loc != None:
                doc_loc_dc = r['doc_loc_dc'] = base64.b64decode(doc_loc)
                locs.add(doc_loc_dc)
        
        sc_lst = _sc_lst
        
        d_loc = {}
        if locs:
            cur.execute('select loc,zone_id from address where loc in ('+','.join(['%s'] * len(locs))+') and flag!=0', tuple(locs))
            for r in cur.fetchall(): d_loc[ r[0] ] = r[1]
        
        lst = []
        for r in sc_lst:
            zid = r['doc_loc'] != None and d_loc.get(r['doc_loc_dc']) or 0
            if zone_id >= 0 and zid != zone_id: continue
            
            doc_js = r['doc_js']
            doc_data = r['doc_data']

            r['zone_id'] = zid
            r['cust_nz'] = (doc_js['customer'] or {}).get('company') or ''
            r['num'] = doc_data[1]
            r['doc_assoc'] = doc_data[2]
            r['doc_date'] = doc_data[3]
            r['doc_amt'] = doc_js['total']
            
            if r['sc_flag'] & REC_FLAG_ACCEPTED and r['doc_crc'] != doc_js.get('crc', 0):
                r['sc_flag'] |= REC_FLAG_CHANGED
            
            r['doc_js'] = r['doc_data'] = r['doc_loc_dc'] = None
            r['doc_sid'] = str(r['doc_sid'])
            
            lst.append(r)
    
        return lst
        
    def fn_get_docs(self):
        dt = self.qsv_int('dt')
        zone_id = self.qsv_int('zone_id')
        clerk_id = self.qsv_int('clerk_id')
        
        m,d = divmod(dt, 100)
        y,m = divmod(m, 100)
        date = datetime.date(y, m, d)
        if date < datetime.date.today(): self.req.exitjs({'err': -9, 'err_s': "Invalid Date"})
        
        ss = 0
        cur = self.cur()
        cur.execute('select ss_val from schedule_special where ss_date=%s and ss_zidx=%s', (dt, zone_id))
        rows = cur.fetchall()
        if rows:
            ss = rows[0][0]
        elif date.weekday() in ZONES[zone_id][1]:
            ss = 1
        
        self.req.writejs({
            'state': ss,
            'date': dt,
            'zone_nz': ZONES[zone_id][0],
            'zone_id': zone_id,
            'lst': self.get_docs(dt, zone_id, clerk_id, 0)
        })

    def fn_print(self):
        sc_ids = map(int, self.req.psv_ustr('sc_ids').split('|'))
        view_only = self.qsv_int('view_only')
        if view_only and len(sc_ids) != 1: return
        
        cur = self.cur()
        docs = self.get_docs_by_sc_ids(sc_ids, True)
        for r in docs:
            dr = dict(zip(('cid','flag','num','assoc','cashier','doc_date','gjs','ijs'), r['doc'][1:]))
            gjs = dr['gjs'] = json.loads(dr['gjs'])
            ijs = dr['ijs'] = json.loads(dr['ijs'])
            dr['doc_date'] = time.strftime("%m/%d/%Y", time.localtime(dr['doc_date']))
            r.update(dr)
            
            type_s = ''
            count_s = ''
            if r['doc_type']:
                d_type = (r['flag'] >> 8) & 0xFF
                d_status = (r['flag'] >> 0) & 0xFF
                
                
                if d_type >= 0 and d_type < len(ORD_TYPE):
                    type_s = ORD_TYPE[d_type]
                else:
                    type_s = 'UNK'
                    
                if d_status == 1:
                    type_s += ' - Reversed'
                elif d_status == 2:
                    type_s += ' - Reversing'
                    
                count_s = 'Item %d, Qty %0.1f' % (gjs['itemcount'], config.round_ex(gjs['qtycount'], 1))
            else:
                if (r['flag'] >> 8) & 0xFF:
                    type_s = 'UNK - '
                else:
                    type_s = 'SO - '
                s = r['flag'] & 0xFF
                if s == 0:
                    type_s += 'Open'
                elif s == 1:
                    type_s += 'Close'
                elif s == 2:
                    type_s += 'Pending'
                if (r['flag'] >> 16) & 0xFF: type_s += ' - **Deleted**'
            
                count_s = 'Item %d, Qty %0.1f/%0.1f' % (
                    gjs['itemcount'],
                    config.round_ex(gjs['sentcount'], 1),
                    config.round_ex(gjs['qtycount'], 1)
                )
            
            r['type_s'] = type_s
            r['count_s'] = count_s
            
            if not view_only:
                loc = None
                if gjs['shipping']:
                    loc = gjs['shipping'].get('loc')
                elif gjs['customer']:
                    loc = gjs['customer'].get('loc')
                
                zidx = 0
                if loc != None:
                    cur.execute('select zone_id from address where loc=%s and flag!=0', (base64.b64decode(loc),))
                    rr = cur.fetchall()
                    if rr: zidx = rr[0][0]
                r['zone_nz'] = ZONES[zidx][0]
            else:
                r['notes'] = d_notes = []
                cur.execute('select dn_ts,dn_flag,dn_val,(select user_name from user where user_id=dn_uid limit 1) as dn_unz from doc_note where doc_type=%s and doc_sid=%s order by dn_id desc limit 20', (
                    r['doc_type'], r['doc_sid']
                    )
                )
                for rr in cur.fetchall():
                    rr = list(rr)
                    rr[0] = time.strftime("%m/%d/%y %I:%M %p", time.localtime(rr[0]))
                    d_notes.append(rr)
                    
        r = {
            'view_only': view_only,
            'auto_print': self.qsv_int('auto_print'),
            'round_ex': config.round_ex,
            'sc_docs': docs,
            'cts_s': time.strftime("%m/%d/%Y %I:%M:%S %p", time.localtime())
        }
        
        self.req.writefile('schedule_batch_print.html', r)
        
        