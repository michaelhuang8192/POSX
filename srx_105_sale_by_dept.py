import config
import datetime
import time
import cPickle
import json
import os
import db as mydb
import const


tp = time.localtime()
frm_ts = int(time.mktime(datetime.date(tp.tm_year, tp.tm_mon, 1).timetuple()))
if tp.tm_mon == 12:
    to_ts = int(time.mktime(datetime.date(tp.tm_year + 1, 1, 1).timetuple()))
else:
    to_ts = int(time.mktime(datetime.date(tp.tm_year, tp.tm_mon + 1, 1).timetuple()))

datafile = os.path.join(os.getcwd(), 'data', "%04d-%02d-%02d_comm.txt" % (tp.tm_year, tp.tm_mon, 1))

mdb = mydb.db_mdb()
cur = mdb.cursor()

cur.execute("select cval from configv2 where ckey='departments' limit 1")
DEPTS = {}
for x in cPickle.loads( cur.fetchall()[0][0] ):
    cate = const.ITEM_D_DEPT.get(x[0].lower())
    DEPTS[x[1]] = (x[0], cate)

ITEM_DEPTS = {}
cur.execute('select sid,deptsid from sync_items')
for r in cur.fetchall(): ITEM_DEPTS[r[0]] = DEPTS.get(r[1])

g_s = {}

USER_MAP = {
    'sales1': 'ray',
    'sales2': 'anthony',
    'sales3': 'joe',
    'sales8': 'nicole',
    'sales5': 'jimmy',
    'sales6': 'sally',
}

cur.execute('select * from sync_receipts where sid_type=0 and (type&0xFF00)<0x0200 and order_date>=%s and order_date<%s', (
    frm_ts, to_ts
    )
)
nzs = cur.column_names
for r in cur:
    r = dict(zip(nzs, r))
    
    items = json.loads(r['items_js'])
    glbs = json.loads(r['global_js'])
    
    rtype = (r['type'] >> 8) & 0xFF
    disc = (100 - glbs['discprc']) / 100
    
    for t in items:
        if t['itemsid'] == 1000000005: continue
        extprice = t['price'] * t['qty'] * disc
        if rtype > 0: extprice = -extprice
        
        cate = (DEPTS.get(t['deptsid']) or [None, None])[1]
        if cate == None: cate = (ITEM_DEPTS.get(t['itemsid']) or [None, None])[1]
        
        clerk = (t['clerk'] or '').lower()
        clerk = USER_MAP.get(clerk, clerk)
        g_s.setdefault(clerk, {}).setdefault(cate, [0, 0, 0])[0] += extprice
        

cPickle.dump( (g_s, []), open(datafile, 'wb'), 1 )
print "Done"

