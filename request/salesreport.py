import json
import time
import config
import datetime
import glob
import os
import const
import json
import cStringIO
import csv

SALES_PERM = 1 << config.USER_PERM_BIT['sales']
ADMIN_PERM = 1 << config.USER_PERM_BIT['admin']

DEFAULT_PERM = 1 << config.USER_PERM_BIT['sales_mgr']
class RequestHandler(App.load('/advancehandler').RequestHandler):
    
    def fn_default(self):
        self.req.writefile('sales_report_frame.html')
    
    
    def fn_cfg(self):
        allowed_users = set(self.get_config_js('sales_report_allowed_users', []))
        sales_users = [ (f_user[0], f_user[1], f_user[1].lower() in allowed_users) for f_user in self.getuserlist() if f_user[2] & SALES_PERM ]
        
        r = {
            'sales_users': sales_users,
        }
        self.req.writefile('sales_report__cfg.html', r)
        
    fn_cfg.PERM = ADMIN_PERM
    
    
    def fn_set_cfg(self):
        sales_users = set([ f_user[1].lower() for f_user in self.getuserlist() if f_user[2] & SALES_PERM ])
        user_nzs = [ user_nz for user_nz in map(unicode.lower, self.req.psv_js('user_nzs')) if user_nz in sales_users ]
        
        self.set_config_js('sales_report_allowed_users', user_nzs)
        self.req.writejs({'err' : 0})
        
    fn_set_cfg.PERM = ADMIN_PERM
    
    def fn_export_csv(self):
        data = [ map(lambda f_x: f_x != None and unicode(f_x) or '', f_r) for f_r in self.req.psv_js('js') ]
        
        fp = cStringIO.StringIO()
        wt = csv.writer(fp)
        for r in data: wt.writerow(r)
        
        self.req.out_headers['content-type'] = 'application/octet-stream'
        self.req.out_headers['content-disposition'] = 'attachment; filename="data.csv"'
        self.req.write( fp.getvalue() )
        
    fn_export_csv.PERM = ADMIN_PERM
    
    def get_data_files(self, months):
        jss = {}
        for i in range(len(months)):
            m = months[i]
            if not m.replace('-', '').isdigit(): return
            datafile = '%s/data/%s_comm_clerks.txt' % (self.req.app.app_dir, m)
            if not os.path.exists(datafile):
                datafile = '%s/data/%s_comm.txt' % (self.req.app.app_dir, m)
                if not os.path.exists(datafile): return
                js = self.get_comm_js(m)
            else:
                js = self.get_comm_clerks_js(m)
                
            jss[m] = js
            
        return jss
    
    
    def fn_sale(self):
        reports_0 = map(lambda n: os.path.basename(n)[:-16], glob.glob(self.req.app.app_dir + '/data/*_comm_clerks.txt'))
        reports_1 = map(lambda n: os.path.basename(n)[:-9], glob.glob(self.req.app.app_dir + '/data/*_comm.txt'))
        
        s = set(reports_0)
        reports = list(s.union(reports_1))
        reports.sort()
        
        if self.user_lvl & ADMIN_PERM:
            sales_users = set([ f_user[1].lower() for f_user in self.getuserlist() if f_user[2] & SALES_PERM ])
        else:
            sales_users = set(self.get_config_js('sales_report_allowed_users', []))
        
        self.req.writefile('sales_report__sale.html', {'reports': reports, 'const': const, 'sales_users': sales_users})
        
    
    def fn_get_sale_data(self):
        months = self.qsv_str('months').split('|')
        
        if self.user_lvl & ADMIN_PERM:
            sales_users = set([ f_user[1].lower() for f_user in self.getuserlist() if f_user[2] & SALES_PERM ])
        else:
            sales_users = set(self.get_config_js('sales_report_allowed_users', []))
                
        jss = {}
        _jss = self.get_data_files(months)
        for m,js in _jss.items():
            jss[m] = dict([ f_v for f_v in js[0].items() if f_v[0] in sales_users ])
        
        self.req.writejs(jss)

    def fn_rect(self):
        reports = map(lambda n: os.path.basename(n)[:-16], glob.glob(self.req.app.app_dir + '/data/*_comm_clerks.txt'))
        reports.sort()
        
        tp = time.localtime()
        dt = "%04d-%02d-%02d" % (tp.tm_year, tp.tm_mon, 1)
        if not reports or reports[-1] != dt: reports.append(dt)
        
        if self.user_lvl & ADMIN_PERM:
            sales_users = set([ f_user[1].lower() for f_user in self.getuserlist() if f_user[2] & SALES_PERM ])
        else:
            sales_users = set(self.get_config_js('sales_report_allowed_users', []))
            
        self.req.writefile('sales_report__rect.html', {'reports': reports, 'const': const, 'sales_users': sales_users})
        
    
    def fn_get_rect_data(self):
        months = self.qsv_str('months').split('|')
        
        if self.user_lvl & ADMIN_PERM:
            sales_users = set([ f_user[1].lower() for f_user in self.getuserlist() if f_user[2] & SALES_PERM ])
        else:
            sales_users = set(self.get_config_js('sales_report_allowed_users', []))
            
        jss = {}
        _jss = self.get_data_files(months)
        for m,js in _jss.items():
            if len(js) <= 2:
                jss[m] = {}
            else:
                jss[m] = dict([ f_v for f_v in js[2].items() if f_v[0] in sales_users ])
        
        self.req.writejs(jss)


