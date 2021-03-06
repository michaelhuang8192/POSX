import json
import os
import time
import datetime
import sys
import config
import re
#import sqlanydb
import data_helper
import hashlib


CFG = {
    'id': 'FORM_C00D1118',
    'name': 'FORM',
    'perm_list': [
    ('access', ''),
    ('admin', ''),
    ]
}
PERM_ADMIN = 1 << 1


class RequestHandler(App.load('/advancehandler').RequestHandler):
    
    def fn_default(self):
        r = {}
        self.req.writefile('form_ctn.html', r)


    def fn_get_form(self):
        self.req.writefile('form/delivery.html', {'config': config})

    def fn_set_state(self):
        js = self.req.psv_js('js')
        f_state = int(js['state'])
        f_id = int(js['id'])
        if f_state not in (1, 2): return

        cur = self.cur()
        if f_state == 1:
            cur.execute('update form set state=%s,dirty_ts=0 where id=%s and state<=%s', (f_state, f_id, f_state))
        elif f_state == 2:
            cur.execute('update form set state=%s,dirty_ts=%s where id=%s and state<%s', (f_state, int(time.time()), f_id, f_state))

        self.req.writejs({'res': cur.rowcount, 'id': f_id})

    def fn_get_form_data(self):
        f_id = self.qsv_int('id')
        cur = self.cur()
        cur.execute('select * from form where id=%s', (f_id,))
        row = cur.fetchall()
        row = dict(zip(cur.column_names, row[0]))
        row['js'] = json.loads(row['js'])
        row['js']['id'] = f_id

        row['state_s'] = str(row['state'])
        row['ts_s'] = time.strftime("%m/%d/%Y %I:%M:%S %p", time.localtime(row['ts']))
        row['schedule_ts_s'] = time.strftime("%m/%d/%Y %I:%M:%S %p", time.localtime(row['schedule_ts']))
        row['dirty_ts_s'] = time.strftime("%m/%d/%Y %I:%M:%S %p", time.localtime(row['dirty_ts']))

        self.req.writejs(row)

    def fn_get_form_list(self):
        f_type = self.req.qsv_int('type')
        f_kw = self.req.qsv_ustr('kw')
        num_rows = 50

        cts = int(time.time())
        if f_kw:
            res = self.search(f_kw, 0, num_rows)
        else:
            cur = self.cur()
            cur.execute('select id,name,user_id,ts,state,dirty_ts,schedule_ts from form where type=%s and (state<2 or %s-dirty_ts<86400) order by schedule_ts asc,id asc limit %s', (f_type, cts, num_rows))
            res = cur.fetchall()

        rows = []
        cnzs = ['id','name','user_id','ts','state','dirty_ts', 'schedule_ts']
        for r in res:
            r = dict(zip(cnzs, r[:len(cnzs)]))
            #rows.append(r)

            ks = time.strftime("%Y-%m-%d %a", time.localtime(r['schedule_ts']))
            if not rows or rows[-1][0] != ks: rows.append((ks, []))
            rows[-1][1].append(r)


        self.req.writejs(rows)

    def fn_delete(self):
        f_id = self.req.psv_int('id')
        cur = self.cur()
        cur.execute('delete from form where id=%s', (f_id, ))
        self.req.writejs({'ret': int(cur.rowcount > 0)})

    fn_delete.PERM = PERM_ADMIN


    MDAYS_LKU = ['other', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
    def fn_save(self):
        js = self.req.psv_js('js')

        f_type = int(js['type'])

        f_name = js['form']['name']
        f_id = int(js.get('id') or 0)
        
        form = js['form']
        kws = ' '.join([
            form.get('address', '').strip(),
            form.get('contact', '').strip(),
            data_helper.parse_phone_num(form.get('phone1', '')),
            data_helper.parse_phone_num(form.get('phone2', ''))
            ]).strip()

        cur = self.cur()
        if f_id:
            cur.execute('select ts,js from form where id=%s', (f_id, ))
            ts_form,js_form = cur.fetchall()[0]
            js_form = json.loads(js_form)
            frm_dt = datetime.date.fromtimestamp(ts_form)
        else:
            frm_dt = datetime.date.today()

        s_day = form['instruction']['date']
        i_day = self.MDAYS_LKU.index(s_day.lower())
        a_days = 0

        if i_day:
            tar_date = datetime.datetime(frm_dt.year, frm_dt.month, frm_dt.day)
            a_days = (i_day - 1 - frm_dt.weekday()) % 7
        else:
            i_date = map(int, form['instruction']['Other_Date'].split('/', 3))
            tar_date = datetime.datetime(i_date[2], i_date[0], i_date[1])

        if form['instruction']['time'][:2].lower() == 'am':
            a_hrs = 8
        else:
            a_hrs = 13

        dts = int(time.mktime((tar_date + datetime.timedelta(a_days, hours=a_hrs)).timetuple()))

        cts = int(time.time())
        form_js = json.dumps(js['form'], separators=(',',':'))
        if f_id:
            h1 = self.hash_dict(js_form)
            h2 = self.hash_dict(js['form'])
            if h1 == h2:
                cur.execute('update form set name=%s,keyword=%s,js=%s,schedule_ts=%s where id=%s and state<2', (
                    f_name, kws, form_js, dts, f_id
                ))
            else:
                cur.execute('update form set name=%s,keyword=%s,js=%s,dirty_ts=%s,schedule_ts=%s where id=%s and state<2', (
                    f_name, kws, form_js, cts, dts, f_id
                ))
        else:
            cur.execute('insert into form values(null, 0, %s, %s, %s, %s, %s, %s, 0, %s)', (
                dts, f_type, f_name, kws, self.user_id, cts, form_js
            ))

            f_id = cur.lastrowid

        self.req.writejs({'id': f_id})

    def hash_dict(self, d):
        lst = sorted(d.items(), key=lambda f_x:f_x[0])
        for i in range(len(lst)):
            k, v = lst[i]
            if type(v) == dict:
                lst[i] = (k, self.hash_dict(v))

        return hashlib.md5(json.dumps(lst)).hexdigest()


    def search(self, kw, mode, num_row=16):
        kws = set(self.regx_kw.sub(u' ', kw).strip().lower().replace(u',', u' ').strip().split(u' '))
        kws.discard(u'')
        if not kws: return
        
        db = self.db()
        cur = db.cur()
        if mode:
            kw = '+' + u' +'.join([k for k in kws])
        else:
            kw = '+' + u' +'.join([k + '* ' + k for k in kws])
        qs = "select id,name,user_id,ts,state,dirty_ts,schedule_ts,(match(name,keyword) against (%s in boolean mode) + match(name) against (%s in boolean mode)*2) as pos from form where match(name,keyword) against (%s in boolean mode) order by pos desc,id desc limit " + str(num_row)
        cur.execute(qs, (kw, kw.replace(u'+', u''), kw))
        res = [ [str(x[0]),] + list(x[1:]) for x in cur.fetchall()]
        
        return res