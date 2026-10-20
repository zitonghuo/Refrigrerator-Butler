"""冰箱管家 local-first backend. Python 3.10+, standard library only."""
import atexit
import base64
from contextlib import contextmanager
import datetime as dt
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import tempfile
import threading
import time
import traceback
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[1]
DB = Path(os.environ.get('FRIDGE_DB', str(ROOT / 'data' / 'fridge.db')))
ZONE = dt.timezone(dt.timedelta(hours=8))
# 识别服务在仓库根目录（与 local-demo 同级），也可用环境变量覆盖。
LOCAL_VISION_ROOT = Path(os.environ.get('LOCAL_VISION_ROOT', str(ROOT.parent / 'vision')))
LOCAL_VISION_PROCESS = None
APP_VERSION = '1.1.0'
SESSION_DAYS = max(1,int(os.environ.get('FRIDGE_SESSION_DAYS','30')))
TASK_RETENTION_DAYS = max(1,int(os.environ.get('FRIDGE_TASK_RETENTION_DAYS','7')))
REQUEST_RETENTION_DAYS = max(1,int(os.environ.get('FRIDGE_REQUEST_RETENTION_DAYS','30')))
# 识别是 CPU/GPU 密集任务，限制同时进行的数量，其余任务在队列里等。
RECOGNITION_SLOTS = threading.BoundedSemaphore(max(1,int(os.environ.get('FRIDGE_MAX_TASKS','2'))))
def now(): return dt.datetime.now(ZONE).isoformat(timespec='seconds')
def expires_at(days=SESSION_DAYS): return (dt.datetime.now(ZONE)+dt.timedelta(days=days)).isoformat(timespec='seconds')
def ensure_column(c,table,column,definition):
    columns={row['name'] for row in c.execute(f'PRAGMA table_info({table})')}
    if column not in columns: c.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
def health():
    report={'status':'ok','version':APP_VERSION,'time':now(),'database':False,'vision':False}
    try:
        with connect() as c:
            c.execute('SELECT 1').fetchone()
            report['database']=True
            report['counts']={t:c.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ('homes','users','items','tasks')}
    except Exception:
        report['status']='degraded'
    endpoint=os.environ.get('RECOGNITION_URL','')
    if endpoint:
        base=endpoint[:-len('/recognize')] if endpoint.endswith('/recognize') else endpoint
        report['vision']=vision_healthy(base.rstrip('/')+'/health')
    else:
        report['vision']=bool(os.environ.get('VISION_URL') and os.environ.get('VISION_MODEL'))
    return report
def vision_healthy(url,timeout=0.6):
    try:
        with urllib.request.urlopen(url,timeout=timeout) as response:
            data=json.load(response)
            return getattr(response,'status',200)==200 and data.get('status')=='ok'
    except Exception: return False
def stop_local_vision():
    global LOCAL_VISION_PROCESS
    process=LOCAL_VISION_PROCESS
    LOCAL_VISION_PROCESS=None
    if process is None or process.poll() is not None: return
    process.terminate()
    try: process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
def ensure_local_vision():
    global LOCAL_VISION_PROCESS
    if os.environ.get('RECOGNITION_URL') or os.environ.get('VISION_URL'): return
    if os.environ.get('FRIDGE_DISABLE_LOCAL_VISION')=='1': return
    port=int(os.environ.get('LOCAL_VISION_PORT','8770'))
    base=f'http://127.0.0.1:{port}'
    recognize_url=base+'/recognize'
    if vision_healthy(base+'/health'):
        os.environ['RECOGNITION_URL']=recognize_url
        print(f'已连接本地食材识别服务 {base}',flush=True)
        return
    python_exe=Path(os.environ.get('LOCAL_VISION_PYTHON',str(LOCAL_VISION_ROOT/'.venv'/'Scripts'/'python.exe')))
    weights=LOCAL_VISION_ROOT/'weights'/'yolov8s.pt'
    if not python_exe.is_file() or not weights.is_file():
        print('未找到本地食材识别环境，识别入口将提示手动录入。',flush=True)
        return
    command=[str(python_exe),'-m','food_recognition.server','--host','127.0.0.1','--port',str(port),'--device',os.environ.get('LOCAL_VISION_DEVICE','auto')]
    LOCAL_VISION_PROCESS=subprocess.Popen(command,cwd=str(LOCAL_VISION_ROOT))
    atexit.register(stop_local_vision)
    deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        if LOCAL_VISION_PROCESS.poll() is not None:
            print('本地食材识别服务启动失败，请检查识别环境日志。',flush=True)
            LOCAL_VISION_PROCESS=None
            return
        if vision_healthy(base+'/health'):
            os.environ['RECOGNITION_URL']=recognize_url
            print(f'本地食材识别服务已启动 {base}',flush=True)
            return
        time.sleep(0.5)
    print('本地食材识别服务启动超时，识别入口暂时不可用。',flush=True)
    stop_local_vision()
@contextmanager
def connect():
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    try:
        with c: yield c
    finally: c.close()
def init():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS homes(id TEXT PRIMARY KEY,name TEXT,invite TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,home TEXT REFERENCES homes(id),name TEXT,codehash TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user TEXT REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY,home TEXT,name TEXT,quantity REAL,unit TEXT,location TEXT,expiry TEXT,source TEXT,created TEXT,version INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,home TEXT,item TEXT,name TEXT,kind TEXT,quantity REAL,unit TEXT,actor TEXT,created TEXT);
        CREATE TABLE IF NOT EXISTS requests(home TEXT,key TEXT,payload TEXT,response TEXT,PRIMARY KEY(home,key));
        CREATE TABLE IF NOT EXISTS shopping(id TEXT PRIMARY KEY,home TEXT,name TEXT,done INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,home TEXT,status TEXT,result TEXT,error TEXT,created TEXT);
        ''')
        # 轻量迁移：老数据库没有这些列时补上，不重建表。
        ensure_column(c,'sessions','expires','TEXT')
        ensure_column(c,'requests','created','TEXT')
        c.execute("UPDATE sessions SET expires=? WHERE expires IS NULL OR expires=''",(expires_at(),))
        c.execute("UPDATE tasks SET status='failed',error='服务重启，请重新上传' WHERE status IN ('queued','processing')")
        # 清理过期会话、旧识别任务和旧幂等记录，避免表无限增长。
        c.execute("DELETE FROM sessions WHERE expires IS NOT NULL AND expires<>'' AND expires<?",(now(),))
        task_cutoff=(dt.datetime.now(ZONE)-dt.timedelta(days=TASK_RETENTION_DAYS)).isoformat(timespec='seconds')
        request_cutoff=(dt.datetime.now(ZONE)-dt.timedelta(days=REQUEST_RETENTION_DAYS)).isoformat(timespec='seconds')
        c.execute("DELETE FROM tasks WHERE status IN ('done','failed') AND created<?",(task_cutoff,))
        c.execute("DELETE FROM requests WHERE created IS NOT NULL AND created!='' AND created<?",(request_cutoff,))
def uid(): return secrets.token_hex(12)
def digest(s): return hashlib.sha256(s.encode()).hexdigest()
def require(ok, message):
    if not ok: raise ValueError(message)
def textval(v, maximum=80):
    require(isinstance(v,str) and 0 < len(v.strip()) <= maximum, '文字为空或超过长度限制')
    return v.strip()
def number(v):
    require(not isinstance(v,bool), '数量格式不正确')
    try: n=float(v)
    except (TypeError,ValueError): raise ValueError('数量格式不正确')
    require(math.isfinite(n) and 0 < n <= 1000000,'数量必须大于 0 且不超过 1000000')
    return n
def expiry(v):
    if not v: return ''
    require(isinstance(v,str),'日期格式不正确')
    dt.date.fromisoformat(v)
    return v
def band(v):
    if not v: return 'unknown'
    end=dt.datetime.combine(dt.date.fromisoformat(v),dt.time(23,59,59),ZONE)
    days=(end-dt.datetime.now(ZONE)).total_seconds()/86400
    return 'expired' if days<0 else 'urgent' if days<=1 else 'soon' if days<=3 else 'week' if days<=7 else 'fresh'
def itemdict(row):
    d=dict(row); d['band']=band(d['expiry']); return d
def log(c,u,item,kind,q):
    c.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?)',(uid(),u['home'],item['id'],item['name'],kind,q,item['unit'],u['name'],now()))

def recognize(task,kind,encoded):
    # 超出并发上限时任务保持 queued，等前面的识别结束再处理。
    with RECOGNITION_SLOTS:
        recognize_locked(task,kind,encoded)

def recognize_locked(task,kind,encoded):
    try:
        with connect() as c: c.execute("UPDATE tasks SET status='processing' WHERE id=?",(task,))
        endpoint=os.environ.get('RECOGNITION_URL','')
        require(endpoint or (os.environ.get('VISION_URL') and os.environ.get('VISION_MODEL')), '未配置识别服务。请手动填写候选清单，或使用明确标注的演示样例。')
        raw=base64.b64decode(encoded,validate=True)
        payload={'kind':kind}
        if kind=='video':
            with tempfile.TemporaryDirectory(prefix='fridge-') as folder:
                p=Path(folder); (p/'input.mp4').write_bytes(raw)
                subprocess.run([os.environ.get('FFMPEG_PATH','ffmpeg'),'-v','error','-i',str(p/'input.mp4'),'-t','30','-vf','fps=1/3,scale=960:-2','-frames:v','10',str(p/'frame-%02d.jpg')],check=True,timeout=60,capture_output=True)
                frames=sorted(p.glob('frame-*.jpg'))
                require(frames,'未能从视频中读取画面')
                payload['images']=[base64.b64encode(f.read_bytes()).decode() for f in frames]
                payload['instruction']='跨帧去重；不要把同一物体的重复画面相加；无法判断数量时 quantity=null。'
        else: payload['images']=[encoded]
        if endpoint:
            # 本地服务可用 FRIDGE_VISION_TOKEN 开启鉴权；外部服务继续用 RECOGNITION_KEY。
            key=os.environ.get('RECOGNITION_KEY') or os.environ.get('FRIDGE_VISION_TOKEN','')
            req=urllib.request.Request(endpoint,json.dumps(payload).encode(),{'Content-Type':'application/json','Authorization':'Bearer '+key})
            with urllib.request.urlopen(req,timeout=90) as response: result=json.load(response)
        else:
            from vision import identify
            result=identify(payload)
        candidates=result.get('candidates')
        require(isinstance(candidates,list) and len(candidates)<=50,'识别服务返回格式不正确')
        clean=[]
        for x in candidates:
            # 置信度原样保留（0–1），前端可据此提示"识别不确定，请核对"。
            confidence=x.get('confidence')
            confidence=round(float(confidence),4) if isinstance(confidence,(int,float)) and 0<=confidence<=1 else None
            clean.append({'name':textval(x.get('name')),'quantity':number(x['quantity']) if x.get('quantity') is not None else '', 'unit':textval(x.get('unit','个'),12),'location':x.get('location') if x.get('location') in ['冷藏','冷冻','常温'] else '冷藏','expiry':expiry(x.get('expiry','')),'source':'label' if x.get('expiry') else 'manual','confidence':confidence})
        with connect() as c: c.execute("UPDATE tasks SET status='done',result=? WHERE id=?",(json.dumps(clean,ensure_ascii=False),task))
    except Exception as e:
        message=str(e) if isinstance(e,ValueError) else '识别失败，请检查服务配置、网络或视频格式后重试'
        with connect() as c: c.execute("UPDATE tasks SET status='failed',error=? WHERE id=?",(message,task))

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def send(self,status,data):
        raw=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(raw)
    def do_GET(self): self.handle_request('GET')
    def do_POST(self): self.handle_request('POST')
    def handle_request(self,method):
        path=urlparse(self.path).path
        if not path.startswith('/api/'):
            if method!='GET': return self.send(405,{'error':'不支持的请求'})
            files={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
            if path not in files: return self.send(404,{'error':'页面不存在'})
            f=ROOT/'web'/files[path]
            self.send_response(200); self.send_header('Content-Type',{'html':'text/html; charset=utf-8','js':'application/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[f.suffix[1:]])
            self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(f.read_bytes()); return
        if path=='/api/health' and method=='GET': return self.send(200,health())
        try:
            size=int(self.headers.get('Content-Length',0)); require(0<=size<=28*1024*1024,'文件过大，请使用 20 MB 以内的素材')
            d=json.loads(self.rfile.read(size)) if size else {}
            require(isinstance(d,dict),'请求必须是对象')
            with connect() as c:
                c.execute('BEGIN IMMEDIATE' if method=='POST' else 'BEGIN')
                if path=='/api/auth' and method=='POST':
                    action=d.get('action')
                    if action=='login':
                        u=c.execute('SELECT * FROM users WHERE codehash=?',(digest(textval(d.get('code'),120)),)).fetchone()
                        require(u is not None,'恢复码不正确')
                        code=None
                    else:
                        name=textval(d.get('name'),24)
                        if action=='create':
                            home=uid(); invite=secrets.token_urlsafe(12)
                            c.execute('INSERT INTO homes VALUES(?,?,?)',(home,textval(d.get('homeName','我的厨房'),30),invite))
                        else:
                            require(action=='join','未知操作')
                            h=c.execute('SELECT * FROM homes WHERE invite=?',(textval(d.get('invite'),100),)).fetchone()
                            require(h is not None,'邀请码不正确'); home=h['id']
                        code=secrets.token_urlsafe(24); user=uid()
                        c.execute('INSERT INTO users VALUES(?,?,?,?)',(user,home,name,digest(code)))
                        u=c.execute('SELECT * FROM users WHERE id=?',(user,)).fetchone()
                    token=secrets.token_urlsafe(32)
                    c.execute('INSERT INTO sessions(token,user,expires) VALUES(?,?,?)',(token,u['id'],expires_at()))
                    result={'token':token,'recoveryCode':code,'expiresIn':SESSION_DAYS*86400}
                else:
                    token=self.headers.get('Authorization','').removeprefix('Bearer ')
                    u=c.execute('SELECT users.* FROM sessions JOIN users ON users.id=sessions.user WHERE token=? AND sessions.expires>?',(token,now())).fetchone()
                    if not u: return self.send(401,{'error':'请先创建家庭或登录'})
                    result=self.route(c,u,path,method,d,token)
            self.send(200,result)
        except (ValueError,KeyError,TypeError) as e: self.send(400,{'error':str(e) or '输入格式不正确'})
        except Exception:
            traceback.print_exc()
            self.send(500,{'error':'服务处理失败，请稍后重试'})
    def route(self,c,u,path,method,d,token):
        home=u['home']
        if path=='/api/state' and method=='GET':
            h=dict(c.execute('SELECT * FROM homes WHERE id=?',(home,)).fetchone())
            return {'home':h,'user':u['name'],'members':[dict(r) for r in c.execute('SELECT name FROM users WHERE home=?',(home,))], 'items':[itemdict(r) for r in c.execute('SELECT * FROM items WHERE home=? AND quantity>0 ORDER BY expiry="",expiry,created DESC',(home,))], 'shopping':[dict(r) for r in c.execute('SELECT * FROM shopping WHERE home=? ORDER BY done,rowid DESC',(home,))], 'events':[dict(r) for r in c.execute('SELECT * FROM events WHERE home=? ORDER BY created DESC,rowid DESC LIMIT 200',(home,))]}
        if path=='/api/task' and method=='GET':
            task=parse_qs(urlparse(self.path).query).get('id',[''])[0]
            row=c.execute('SELECT * FROM tasks WHERE id=? AND home=?',(task,home)).fetchone(); require(row is not None,'任务不存在')
            result=dict(row); result['result']=json.loads(result['result'] or '[]'); return result
        require(method=='POST','接口不存在')
        if path=='/api/logout': c.execute('DELETE FROM sessions WHERE token=?',(token,)); return {'ok':True}
        if path=='/api/invite/rotate':
            code=secrets.token_urlsafe(12); c.execute('UPDATE homes SET invite=? WHERE id=?',(code,home)); return {'invite':code}
        if path=='/api/recognize':
            require(d.get('kind') in ['photo','receipt','video'],'入口不正确')
            encoded=d.get('data',''); require(isinstance(encoded,str) and len(encoded)>0,'请上传文件')
            base64.b64decode(encoded,validate=True)
            task=uid(); c.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?)',(task,home,'queued','[]','',now()))
            # Start only after the insert is committed so worker updates cannot race it.
            c.commit(); threading.Thread(target=recognize,args=(task,d['kind'],encoded),daemon=True).start()
            return {'id':task}
        if path=='/api/items/add':
            key=textval(d.get('key'),120); payload=json.dumps(d.get('items'),sort_keys=True,ensure_ascii=False)
            prior=c.execute('SELECT * FROM requests WHERE home=? AND key=?',(home,key)).fetchone()
            if prior:
                require(hmac.compare_digest(prior['payload'].encode(),payload.encode()),'提交标识已用于不同内容，请刷新后重试')
                return json.loads(prior['response'])
            require(isinstance(d.get('items'),list) and 1<=len(d['items'])<=50,'请添加 1 至 50 项食材')
            ids=[]
            for x in d['items']:
                name=textval(x.get('name')); q=number(x.get('quantity')); unit=textval(x.get('unit'),12)
                location=x.get('location'); require(location in ['冷藏','冷冻','常温'],'储存位置不正确')
                date=expiry(x.get('expiry','')); source=x.get('source','manual'); require(source in ['manual','label','estimate'],'日期来源不正确')
                item=uid(); c.execute('INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?,1)',(item,home,name,q,unit,location,date,source,now()))
                log(c,u,{'id':item,'name':name,'unit':unit},'入库',q); ids.append(item)
            result={'ids':ids}; c.execute('INSERT INTO requests(home,key,payload,response,created) VALUES(?,?,?,?,?)',(home,key,payload,json.dumps(result),now())); return result
        if path=='/api/items/change':
            r=c.execute('SELECT * FROM items WHERE id=? AND home=?',(d.get('id'),home)).fetchone(); require(r is not None,'食材不存在')
            require(d.get('version')==r['version'],'库存已被其他成员更新，请刷新后重试')
            kind=d.get('kind'); require(kind in ['消耗','丢弃','盘点'],'操作类型不正确')
            if kind=='盘点':
                q=0 if d.get('quantity') in [0,'0'] else number(d.get('quantity')); change=q-r['quantity']
            else:
                amount=number(d.get('quantity')); require(amount<=r['quantity'],'数量超过当前库存'); q=round(r['quantity']-amount,6); change=amount
            c.execute('UPDATE items SET quantity=?,version=version+1 WHERE id=?',(q,r['id'])); log(c,u,r,kind,change); return {'ok':True}
        if path=='/api/shopping/add':
            c.execute('INSERT INTO shopping VALUES(?,?,?,0)',(uid(),home,textval(d.get('name')))); return {'ok':True}
        if path=='/api/shopping/toggle':
            r=c.execute('SELECT * FROM shopping WHERE id=? AND home=?',(d.get('id'),home)).fetchone(); require(r is not None,'采购项不存在')
            c.execute('UPDATE shopping SET done=? WHERE id=?',(0 if r['done'] else 1,r['id'])); return {'ok':True}
        if path=='/api/demo':
            require(not c.execute('SELECT 1 FROM items WHERE home=?',(home,)).fetchone(),'仅空家庭可加载样例，避免覆盖真实记录')
            today=dt.date.today()
            for name,q,unit,loc,days in [('西兰花',1,'颗','冷藏',1),('鲜牛奶',2,'盒','冷藏',2),('鸡蛋',8,'个','冷藏',12),('番茄',3,'个','冷藏',4),('鸡胸肉',2,'袋','冷冻',20),('燕麦',1,'罐','常温',40)]:
                item=uid(); date=(today+dt.timedelta(days=days)).isoformat()
                c.execute('INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?,1)',(item,home,name,q,unit,loc,date,'estimate',now())); log(c,u,{'id':item,'name':name,'unit':unit},'演示入库',q)
            return {'ok':True}
        raise ValueError('接口不存在')

if __name__=='__main__':
    init(); ensure_local_vision(); host=os.environ.get('HOST','127.0.0.1'); port=int(os.environ.get('PORT','8765'))
    print(f'冰箱管家已启动 http://{host}:{port}',flush=True)
    server=ThreadingHTTPServer((host,port),Handler)
    if os.environ.get('FRIDGE_OPEN_BROWSER')=='1':
        threading.Timer(1.0,lambda: webbrowser.open(f'http://127.0.0.1:{port}')).start()
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        server.server_close()
        stop_local_vision()
