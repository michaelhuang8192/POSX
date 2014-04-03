import config
import datetime
import time
import cPickle
import json
import os
import db as mydb

mdb = mydb.db_mdb()
cur = mdb.cursor()

g_items = {}

cur.execute('select * from sync_receipts where sid_type=0 and (type&0xFF00)<0x0200')
nzs = cur.column_names
for r in cur:
    r = dict(zip(nzs, r))
    
    items = json.loads(r['items_js'])
    glbs = json.loads(r['global_js'])
    
    rtype = (r['type'] >> 8) & 0xFF
    disc = (100 - glbs['discprc']) / 100
    
    tp = time.localtime(r['order_date'])
    for t in items:
        item = g_items.get(t['itemsid'])
        if not item: item = g_items[ t['itemsid'] ] = [set(), set(), {}, None]
        item[0].add(t['itemno'])
        item[1].add(t['desc1'])
        stat = item[2].setdefault(tp.tm_year * 100 + tp.tm_mon, [0, 0, 0])
        total_base_qty = t['nunits'] * t['qty']
        total_price =  t['price'] * t['qty'] * disc
        total_cost = t['cost'] * t['qty']
        
        if rtype > 0:
            total_base_qty = -total_base_qty
            total_price = -total_price
            total_cost = -total_cost
            
        stat[0] += total_base_qty
        stat[1] += total_price
        stat[2] += total_cost


cur.execute('select * from sorder where (ord_flag&8)!=0')
nzs = cur.column_names
for r in cur:
    r = dict(zip(nzs, r))
    
    items = json.loads(r['ord_items_js'])
    glbs = json.loads(r['ord_global_js'])
    
    rtype = r['ord_flag'] & (1 << 1)
    disc = (100 - glbs['disc']) / 100
    
    tp = time.localtime(r['ord_order_date'])
    for t in items:
        item = g_items.get(t['id'])
        if not item: item = g_items[ t['id'] ] = [set(), set(), {}, None]
        item[0].add(t['num'])
        item[1].add(t['in_desc'])
        stat = item[2].setdefault(tp.tm_year * 100 + tp.tm_mon, [0, 0, 0])
        total_base_qty = t['in_base_qty']
        total_price =  t['in_price'] * t['in_qty'] * disc
        total_cost = t['prev_qty'][4] * total_base_qty
        
        if rtype > 0:
            total_base_qty = -total_base_qty
            total_price = -total_price
            total_cost = -total_cost
            
        stat[0] += total_base_qty
        stat[1] += total_price
        stat[2] += total_cost


cur.execute('select * from sync_items')
nzs = cur.column_names
for r in cur:
    r = dict(zip(nzs, r))
    
    item = g_items.get(r['sid'])
    if not item: continue
    l_qty = json.loads(r['detail'])['qty']
    item[3] = {
        'num': r['num'],
        'name': r['name'],
        'l_qty': l_qty,
        'status': r['status'],
        'deptsid': r['deptsid'],
    }

for item in g_items.values():
    item[0] = tuple(item[0])
    item[1] = tuple(item[1])
    d_status = item[2]
    item[2] = [ [f_k] + f_v for f_k,f_v in sorted(d_status.items(), key=lambda f_x:f_x[0]) ]
    
fnz = os.path.join(config.DATA_DIR, 'items_stat.txt')
cPickle.dump(g_items, open(fnz, 'wb'), 1)

print "Done"


