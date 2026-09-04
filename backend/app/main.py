from __future__ import annotations
import asyncio, os, socket, ssl, time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import declarative_base, sessionmaker

ROOT=Path(__file__).resolve().parents[2]
DATA=Path(os.getenv('NETSCREEN_DATA_DIR',ROOT/'data')); DATA.mkdir(parents=True,exist_ok=True)
DB=os.getenv('NETSCREEN_DATABASE_URL',f'sqlite:///{DATA}/netscreen.db')
engine=create_engine(DB,connect_args={'check_same_thread':False} if DB.startswith('sqlite') else {})
Session=sessionmaker(bind=engine,autoflush=False); Base=declarative_base()
def now(): return datetime.now(timezone.utc).replace(tzinfo=None)
class Monitor(Base):
 __tablename__='monitors'; id=Column(Integer,primary_key=True); name=Column(String(120),nullable=False); target=Column(String(500),nullable=False); type=Column(String(12),nullable=False); interval=Column(Integer,default=60); timeout=Column(Integer,default=5); enabled=Column(Boolean,default=True); status=Column(String(12),default='unknown'); latency=Column(Float); packet_loss=Column(Float); http_status=Column(Integer); error=Column(Text); method=Column(String(12)); last_check=Column(DateTime); last_success=Column(DateTime); last_failure=Column(DateTime); created_at=Column(DateTime,default=now)
class Result(Base):
 __tablename__='results'; id=Column(Integer,primary_key=True); monitor_id=Column(Integer,ForeignKey('monitors.id',ondelete='CASCADE')); timestamp=Column(DateTime,default=now); status=Column(String(12)); latency=Column(Float); packet_loss=Column(Float); http_status=Column(Integer); error=Column(Text)
class Alert(Base):
 __tablename__='alerts'; id=Column(Integer,primary_key=True); monitor_id=Column(Integer); type=Column(String(24)); severity=Column(String(12)); message=Column(Text); read=Column(Boolean,default=False); created_at=Column(DateTime,default=now)
Base.metadata.create_all(engine)
class MonitorIn(BaseModel):
 name:str=Field(min_length=1,max_length=120); target:str=Field(min_length=1,max_length=500); type:Literal['ping','http','https','dns']='ping'; interval:int=Field(60,ge=10,le=86400); timeout:int=Field(5,ge=1,le=60); enabled:bool=True
 @field_validator('name','target')
 @classmethod
 def strip(cls,v): return v.strip()
class SettingsIn(BaseModel): language:Literal['en','fa']|None=None; theme:Literal['dark','light']|None=None

def clean_target(target,kind):
 t=target.strip()
 if kind in ('http','https'):
  if '://' not in t:t=('https://' if kind=='https' else 'http://')+t
  if not t.startswith(('http://','https://')):raise ValueError('Use an http:// or https:// URL.')
  return t
 return t.split('://')[-1].split('/')[0].rstrip('.')
async def probe(m):
 start=time.perf_counter(); typ=m.type; target=m.target
 try:
  if typ=='dns':
   addrs=await asyncio.to_thread(lambda:socket.gethostbyname_ex(target)[2]); latency=(time.perf_counter()-start)*1000
   return {'status':'degraded' if latency>300 else 'online','latency':round(latency,2),'error':None,'method':'dns','addresses':addrs}
  if typ in ('http','https'):
   async with httpx.AsyncClient(timeout=m.timeout,follow_redirects=True) as c:r=await c.get(target)
   latency=(time.perf_counter()-start)*1000; ok=200<=r.status_code<400
   return {'status':'online' if ok and latency<1500 else ('degraded' if ok else 'offline'),'latency':round(latency,2),'http_status':r.status_code,'error':None if ok else f'HTTP {r.status_code}','method':'http'}
  try:
   proc=await asyncio.create_subprocess_exec('ping','-c','1','-W',str(m.timeout),target,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT); out=(await asyncio.wait_for(proc.communicate(),m.timeout+2))[0].decode(errors='ignore'); ok=proc.returncode==0
   import re; hit=re.search(r'time[=<]([\d.]+)',out); latency=float(hit.group(1)) if hit else None
   return {'status':'online' if ok else 'offline','latency':latency,'packet_loss':0 if ok else 100,'error':None if ok else 'Host did not answer.','method':'icmp'}
  except Exception:
   socket.create_connection((target,443),m.timeout).close(); latency=(time.perf_counter()-start)*1000
   return {'status':'online','latency':round(latency,2),'packet_loss':0,'error':None,'method':'tcp'}
 except Exception as e:return {'status':'offline','latency':None,'packet_loss':100 if typ=='ping' else None,'error':str(e)[:500],'method':typ}
def dto(m): return {'id':m.id,'name':m.name,'target':m.target,'type':m.type,'interval':m.interval,'timeout':m.timeout,'enabled':m.enabled,'status':m.status,'latency':m.latency,'packet_loss':m.packet_loss,'http_status':m.http_status,'error':m.error,'method':m.method,'last_check':m.last_check,'last_success':m.last_success,'last_failure':m.last_failure,'created_at':m.created_at}
def persist(mid,r):
 db=Session();m=db.get(Monitor,mid)
 if not m:return
 old=m.status; t=now();m.status=r['status'];m.latency=r.get('latency');m.packet_loss=r.get('packet_loss');m.http_status=r.get('http_status');m.error=r.get('error');m.method=r.get('method');m.last_check=t
 if m.status=='offline':m.last_failure=t
 else:m.last_success=t
 db.add(Result(monitor_id=mid,status=m.status,latency=m.latency,packet_loss=m.packet_loss,http_status=m.http_status,error=m.error))
 if m.status=='offline' and old!='offline':db.add(Alert(monitor_id=mid,type='down',severity='critical',message=f'{m.name} is offline'))
 if old=='offline' and m.status in ('online','degraded'):db.add(Alert(monitor_id=mid,type='recovery',severity='info',message=f'{m.name} recovered'))
 db.commit();db.close()
async def scheduler():
 while True:
  db=Session(); mons=db.scalars(select(Monitor).where(Monitor.enabled.is_(True))).all(); db.close()
  for m in mons:
   if not m.last_check or (now()-m.last_check).total_seconds()>=m.interval:
    r=await probe(m);await asyncio.to_thread(persist,m.id,r)
  await asyncio.sleep(5)
@asynccontextmanager
async def life(app):
 task=None
 if os.getenv('NETSCREEN_SCHEDULER','1')!='0':task=asyncio.create_task(scheduler())
 yield
 if task:task.cancel()
app=FastAPI(title='NetScreen API',version='1.0.0',lifespan=life)
@app.get('/api/health')
def health():return {'status':'ok','version':'1.0.0','database':'ok','scheduler':os.getenv('NETSCREEN_SCHEDULER','1')!='0'}
@app.get('/api/stats')
def stats():
 db=Session();ms=db.scalars(select(Monitor)).all(); alerts=db.scalars(select(Alert).where(Alert.read.is_(False))).all(); counts={x:sum(m.status==x for m in ms) for x in ('online','degraded','offline','unknown')}; return {'total_monitors':len(ms),'enabled_monitors':sum(m.enabled for m in ms),'counts':counts,'active_alerts':len(alerts),'recent_alerts':[{'id':a.id,'type':a.type,'severity':a.severity,'message':a.message,'created_at':a.created_at} for a in alerts[-8:]]}
@app.get('/api/monitors')
def monitors():
 db=Session();return [dto(m) for m in db.scalars(select(Monitor).order_by(Monitor.name)).all()]
@app.post('/api/monitors',status_code=201)
def create(x:MonitorIn):
 try:t=clean_target(x.target,x.type)
 except ValueError as e:raise HTTPException(422,str(e))
 db=Session();m=Monitor(name=x.name,target=t,type=x.type,interval=x.interval,timeout=x.timeout,enabled=x.enabled);db.add(m);db.commit();db.refresh(m);return dto(m)
@app.get('/api/monitors/{mid}')
def get(mid:int):
 db=Session();m=db.get(Monitor,mid)
 if not m:raise HTTPException(404,'Monitor not found')
 return dto(m)
@app.put('/api/monitors/{mid}')
def update(mid:int,x:MonitorIn):
 db=Session();m=db.get(Monitor,mid)
 if not m:raise HTTPException(404,'Monitor not found')
 m.name=x.name;m.target=clean_target(x.target,x.type);m.type=x.type;m.interval=x.interval;m.timeout=x.timeout;m.enabled=x.enabled;db.commit();db.refresh(m);return dto(m)
@app.delete('/api/monitors/{mid}',status_code=204)
def delete(mid:int):
 db=Session();m=db.get(Monitor,mid)
 if not m:raise HTTPException(404,'Monitor not found')
 db.delete(m);db.commit()
@app.post('/api/monitors/{mid}/check')
async def check(mid:int):
 db=Session();m=db.get(Monitor,mid)
 if not m:raise HTTPException(404,'Monitor not found')
 r=await probe(m);await asyncio.to_thread(persist,mid,r);db.refresh(m);return {'monitor':dto(m),'result':r}
@app.get('/api/monitors/{mid}/history')
def history(mid:int):
 db=Session();return [{'timestamp':r.timestamp,'status':r.status,'latency':r.latency,'error':r.error} for r in db.scalars(select(Result).where(Result.monitor_id==mid).order_by(Result.timestamp.desc()).limit(300)).all()]
@app.get('/api/alerts')
def alerts():
 db=Session();return [{'id':a.id,'monitor_id':a.monitor_id,'type':a.type,'severity':a.severity,'message':a.message,'read':a.read,'created_at':a.created_at} for a in db.scalars(select(Alert).order_by(Alert.created_at.desc()).limit(200)).all()]
@app.put('/api/alerts/{aid}/read')
def read_alert(aid:int):
 db=Session();a=db.get(Alert,aid)
 if not a:raise HTTPException(404,'Alert not found')
 a.read=True;db.commit();return {'ok':True}
@app.get('/api/settings')
def settings():return {'settings':{'language':'en','theme':'dark'},'telegram_configured':bool(os.getenv('TELEGRAM_BOT_TOKEN') and os.getenv('TELEGRAM_CHAT_ID'))}
frontend=ROOT/'frontend'; docs=ROOT/'docs'
if docs.is_dir():app.mount('/guide',StaticFiles(directory=docs,html=True),name='guide')
if frontend.is_dir():app.mount('/',StaticFiles(directory=frontend,html=True),name='frontend')
