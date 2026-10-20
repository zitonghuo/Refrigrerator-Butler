import base64
import concurrent.futures
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

spec=importlib.util.spec_from_file_location('fridge',Path(__file__).resolve().parents[1]/'server'/'app.py')
app=importlib.util.module_from_spec(spec); spec.loader.exec_module(app)
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))

class Recognition(BaseHTTPRequestHandler):
    def do_POST(self):
        d=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        result={'candidates':[{'name':'测试番茄','quantity':None,'unit':'个','confidence':0.42}]}
        if 'messages' in d: result={'choices':[{'message':{'content':json.dumps(result)}}]}
        self.send_response(200); self.end_headers(); self.wfile.write(json.dumps(result).encode())
    def log_message(self,*a): pass

class Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(); app.DB=Path(cls.temp.name)/'test.db'; app.init()
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        cls.url='http://127.0.0.1:'+str(cls.server.server_port)+'/api/'
        threading.Thread(target=cls.server.serve_forever,daemon=True).start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.temp.cleanup()
    def call(self,path,data=None,token=''):
        req=urllib.request.Request(self.url+path,json.dumps(data).encode() if data is not None else None,{'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:return e.code,json.load(e)
    def user(self):
        status,r=self.call('auth',{'action':'create','name':'测试用户','homeName':'测试厨房'})
        self.assertEqual(status,200); return r
    def add(self,token,key='batch',q=1):
        return self.call('items/add',{'key':key,'items':[{'name':'番茄','quantity':q,'unit':'个','location':'冷藏','expiry':'2030-01-01','source':'manual'}]},token)
    def test_auth_and_recovery(self):
        u=self.user(); self.assertEqual(self.call('state')[0],401)
        status,r=self.call('auth',{'action':'login','code':u['recoveryCode']}); self.assertEqual(status,200)
        self.assertEqual(self.call('state',token=r['token'])[0],200)
        self.call('logout',{},r['token']); self.assertEqual(self.call('state',token=r['token'])[0],401)
    def test_idempotence_and_atomic_validation(self):
        t=self.user()['token']; first=self.add(t); second=self.add(t)
        self.assertEqual(first,second); self.assertEqual(len(self.call('state',token=t)[1]['items']),1)
        self.assertEqual(self.add(t,q=2)[0],400)
        status,_=self.call('items/add',{'key':'bad','items':[{'name':'梨','quantity':2,'unit':'个','location':'常温'},{'name':'坏项','quantity':-2,'unit':'个','location':'常温'}]},t)
        self.assertEqual(status,400);self.assertEqual(len(self.call('state',token=t)[1]['items']),1)
    def test_household_isolation(self):
        a=self.user()['token']; b=self.user()['token']; self.add(a)
        row=self.call('state',token=a)[1]['items'][0]
        self.assertEqual(self.call('state',token=b)[1]['items'],[])
        self.assertEqual(self.call('items/change',{'id':row['id'],'version':1,'kind':'消耗','quantity':1},b)[0],400)
        self.call('shopping/add',{'name':'鸡蛋'},a); shop=self.call('state',token=a)[1]['shopping'][0]
        self.assertEqual(self.call('shopping/toggle',{'id':shop['id']},b)[0],400)
    def test_join_and_concurrent_decrement(self):
        a=self.user()['token']; home=self.call('state',token=a)[1]['home']; self.add(a)
        b=self.call('auth',{'action':'join','name':'成员乙','invite':home['invite']})[1]['token']
        row=self.call('state',token=b)[1]['items'][0]
        data={'id':row['id'],'version':row['version'],'kind':'消耗','quantity':1}
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda t:self.call('items/change',data,t)[0],[a,b]))
        self.assertEqual(sorted(results),[200,400]);self.assertEqual(self.call('state',token=a)[1]['items'],[])
        self.call('invite/rotate',{},a)
        self.assertEqual(self.call('auth',{'action':'join','name':'丙','invite':home['invite']})[0],400)
    def test_inventory_and_purchase(self):
        t=self.user()['token']; self.add(t,q=4); row=self.call('state',token=t)[1]['items'][0]
        self.assertEqual(self.call('items/change',{'id':row['id'],'version':1,'kind':'盘点','quantity':2},t)[0],200)
        state=self.call('state',token=t)[1];self.assertEqual(state['items'][0]['quantity'],2)
        self.assertEqual(state['events'][0]['quantity'],-2)
        self.call('shopping/add',{'name':'牛奶'},t);shop=self.call('state',token=t)[1]['shopping'][0]
        self.call('shopping/toggle',{'id':shop['id']},t);self.assertEqual(self.call('state',token=t)[1]['shopping'][0]['done'],1)
    def test_nonfinite_invalid_date_and_empty(self):
        t=self.user()['token']; self.assertEqual(self.add(t,q=float('nan'))[0],400)
        self.assertEqual(self.add(t,q=0)[0],400)
        self.assertEqual(self.call('items/add',{'key':'e','items':[]},t)[0],400)
        with self.assertRaises(ValueError):app.expiry('2026-02-30')
        self.assertEqual(app.band(''),'unknown');self.assertEqual(app.band('2020-01-01'),'expired')
    def test_recognition_failure_and_task_isolation(self):
        saved=os.environ.pop('RECOGNITION_URL',None)
        try:
            t=self.user()['token']; b=self.user()['token']; status,r=self.call('recognize',{'kind':'photo','data':base64.b64encode(b'test').decode()},t)
            self.assertEqual(status,200);self.assertEqual(self.call('task?id='+r['id'],token=b)[0],400)
            for _ in range(50):
                task=self.call('task?id='+r['id'],token=t)[1]
                if task['status']=='failed':break
                time.sleep(.02)
            self.assertEqual(task['status'],'failed'); self.assertIn('未配置',task['error'])
        finally:
            if saved:os.environ['RECOGNITION_URL']=saved
    def test_recognition_adapter(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Recognition);threading.Thread(target=server.serve_forever,daemon=True).start()
        previous=os.environ.get('RECOGNITION_URL');os.environ['RECOGNITION_URL']='http://127.0.0.1:'+str(server.server_port)
        try:
            t=self.user()['token']; _,r=self.call('recognize',{'kind':'receipt','data':base64.b64encode(b'test').decode()},t)
            for _ in range(100):
                task=self.call('task?id='+r['id'],token=t)[1]
                if task['status'] in ['done','failed']:break
                time.sleep(.02)
            self.assertEqual(task['status'],'done');self.assertEqual(task['result'][0]['quantity'],'')
            self.assertEqual(task['result'][0]['confidence'],0.42)
            self.assertEqual(self.call('state',token=t)[1]['items'],[])
        finally:
            if previous:os.environ['RECOGNITION_URL']=previous
            else:os.environ.pop('RECOGNITION_URL',None)
            server.shutdown();server.server_close()

    def test_vision_compatible_adapter(self):
        from vision import identify
        server=ThreadingHTTPServer(('127.0.0.1',0),Recognition);threading.Thread(target=server.serve_forever,daemon=True).start()
        old={k:os.environ.get(k) for k in ['VISION_URL','VISION_MODEL']}
        os.environ['VISION_URL']='http://127.0.0.1:'+str(server.server_port);os.environ['VISION_MODEL']='test-only-model'
        try:
            result=identify({'kind':'photo','images':[base64.b64encode(b'test').decode()]})
            self.assertEqual(result['candidates'][0]['name'],'测试番茄')
        finally:
            for k,v in old.items():
                if v is None:os.environ.pop(k,None)
                else:os.environ[k]=v
            server.shutdown();server.server_close()

    def test_health_and_session_expiry(self):
        status,report=self.call('health')
        self.assertEqual(status,200);self.assertTrue(report['database']);self.assertIn('vision',report)
        u=self.user();self.assertIn('expiresIn',u)
        self.assertEqual(self.call('state',token=u['token'])[0],200)
        with app.connect() as c:
            c.execute("UPDATE sessions SET expires=? WHERE token=?",('2000-01-01T00:00:00+08:00',u['token']))
        self.assertEqual(self.call('state',token=u['token'])[0],401)

    def test_task_and_request_retention(self):
        u=self.user();home=self.call('state',token=u['token'])[1]['home']['id']
        with app.connect() as c:
            c.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?)",('old-task',home,'done','[]','','2000-01-01T00:00:00+08:00'))
            c.execute("INSERT INTO requests(home,key,payload,response,created) VALUES(?,?,?,?,?)",(home,'old-key','{}','{}','2000-01-01T00:00:00+08:00'))
        app.init()
        with app.connect() as c:
            self.assertIsNone(c.execute("SELECT 1 FROM tasks WHERE id='old-task'").fetchone())
            self.assertIsNone(c.execute("SELECT 1 FROM requests WHERE key='old-key'").fetchone())

    @unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg is optional and unavailable')
    def test_video_frame_pipeline(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Recognition);threading.Thread(target=server.serve_forever,daemon=True).start()
        previous=os.environ.get('RECOGNITION_URL');os.environ['RECOGNITION_URL']='http://127.0.0.1:'+str(server.server_port)
        try:
            video=Path(self.temp.name)/'test.mp4'
            subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=green:s=64x64:d=4','-pix_fmt','yuv420p',str(video)],check=True,timeout=30,capture_output=True)
            t=self.user()['token'];status,r=self.call('recognize',{'kind':'video','data':base64.b64encode(video.read_bytes()).decode()},t)
            self.assertEqual(status,200)
            for _ in range(200):
                task=self.call('task?id='+r['id'],token=t)[1]
                if task['status'] in ['done','failed']:break
                time.sleep(.05)
            self.assertEqual(task['status'],'done',task.get('error'))
        finally:
            if previous:os.environ['RECOGNITION_URL']=previous
            else:os.environ.pop('RECOGNITION_URL',None)
            server.shutdown();server.server_close()

if __name__=='__main__':unittest.main(verbosity=2)
