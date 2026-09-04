import os
os.environ['NETSCREEN_SCHEDULER']='0'
from fastapi.testclient import TestClient
from app.main import app

def test_health_and_stats():
 with TestClient(app) as c:
  assert c.get('/api/health').status_code==200
  body=c.get('/api/stats').json(); assert 'counts' in body

def test_monitor_crud_and_validation():
 with TestClient(app) as c:
  x=c.post('/api/monitors',json={'name':'Local DNS','target':'localhost','type':'dns'}); assert x.status_code==201
  mid=x.json()['id']; assert c.get(f'/api/monitors/{mid}').status_code==200
  assert c.put(f'/api/monitors/{mid}',json={'name':'Updated','target':'localhost','type':'dns'}).status_code==200
  assert c.delete(f'/api/monitors/{mid}').status_code==204

def test_invalid_type_is_rejected():
 with TestClient(app) as c:
  assert c.post('/api/monitors',json={'name':'Bad','target':'x','type':'telnet'}).status_code==422
