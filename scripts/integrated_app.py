"""Automatic tactical room + grounded per-plan explanations, one deployment."""
import argparse
from collections import OrderedDict, deque
from concurrent.futures import Future
import json
import os
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from pydantic import ConfigDict
from serve_coach_room import RoomRequest, create_room
from subintel.plan_narrative import explain_plan, identified, chosen_plan

ROOT=Path(__file__).resolve().parents[1]


class ExplainRequest(RoomRequest):
    model_config=ConfigDict(extra='forbid')
    plan_id: str
    audience: str='fan'
    lang: str='en'


def annotate(snapshot):
    plans=identified(snapshot)
    swaps=[p for p in plans if p['plan_kind']=='SUBSTITUTION']
    selected=snapshot.get('selected')
    selected_id=(f"swap:{selected['out_player']['id']}:{selected['in_player']['id']}" if selected else
                 'tactical' if snapshot['recommendation']=='TACTICAL_ADJUSTMENT' else 'wait')
    return dict(snapshot,alternatives=swaps,selected_plan_id=selected_id,
                tactical_plan=next((p for p in plans if p['plan_id']=='tactical'),None),
                api_version='integrated-room-v1')


class ExplanationCache:
    """Bounded TTL cache, single-flight per key, global cooldown and call budget.

    Process-local: restarting or scaling creates a new budget. This is not a
    claim of a lifetime upper bound on paid calls.
    """
    def __init__(self, fn, max_entries=256, clock=time.monotonic, calls_per_minute=24):
        self.fn,self.max_entries,self.clock,self.limit=fn,max_entries,clock,calls_per_minute
        self.lock=threading.Lock();self.pending={};self.cache=OrderedDict();self.calls=deque()
        self.cooldown_until=0.;self.slots=threading.BoundedSemaphore(2)

    def get(self,key,*args):
        with self.lock:
            now=self.clock()
            if key in self.cache:
                expires,value=self.cache[key]
                if expires>now:
                    self.cache.move_to_end(key)
                    return dict(value,cached=True)
                del self.cache[key]
            if key in self.pending:
                future=self.pending[key];owner=False
            else:
                future=Future();self.pending[key]=future;owner=True
        if not owner:
            return dict(future.result(timeout=20),cached=True)
        try:
            with self.lock:
                now=self.clock()
                while self.calls and self.calls[0]<=now-60:self.calls.popleft()
                allowed=now>=self.cooldown_until and len(self.calls)<self.limit
                if allowed:self.calls.append(now)
            acquired=allowed and self.slots.acquire(timeout=.2)
            if acquired:
                try: value=self.fn(*args)
                finally:self.slots.release()
            else:
                # No provider invocation while cooling down, busy or over budget.
                from subintel.plan_narrative import fact_bundle,sentences,default_ids
                snapshot,plan_id,audience,lang=args
                facts=fact_bundle(snapshot,plan_id);bank=sentences(facts,audience,lang);ids=default_ids(bank,audience)
                value=dict(text=' '.join(bank[k] for k in ids),source='template',note='LLM_COOLDOWN',
                    audience=audience,lang=lang,plan_id=plan_id,facts=facts,fact_ids=ids,rendering='VERIFIED_FACT_SENTENCES',model=None)
            with self.lock:
                if value.get('note')=='LLM_UNAVAILABLE':self.cooldown_until=self.clock()+15
                ttl=600 if value['source']=='llm' else 30
                self.cache[key]=(self.clock()+ttl,value)
                while len(self.cache)>self.max_entries:self.cache.popitem(last=False)
            future.set_result(value)
            return dict(value,cached=False)
        except Exception as error:
            future.set_exception(error)
            raise
        finally:
            with self.lock:self.pending.pop(key,None)


class IntegratedApp:
    def __init__(self,bootstrap,evaluate,explain_fn=explain_plan):
        self.bootstrap,self.evaluate=bootstrap,evaluate
        self.explanations=ExplanationCache(explain_fn)

    def snapshot(self,request):
        return annotate(self.evaluate(request.match_id,request.team_id,request.minute,request.config.model_dump_json()))

    def explanation(self,request):
        if request.audience not in ('fan','analyst','broadcaster') or request.lang not in ('en','he'):
            raise ValueError('unsupported locale or audience')
        snapshot=self.snapshot(request)
        chosen_plan(snapshot,request.plan_id)  # validation before cache/provider
        key=(request.match_id,request.team_id,request.minute,request.config.model_dump_json(),request.plan_id,request.audience,request.lang)
        return self.explanations.get(key,snapshot,request.plan_id,request.audience,request.lang)


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def send(self,status,body,mime='application/json; charset=utf-8'):
            if not isinstance(body,bytes):body=json.dumps(body,ensure_ascii=False,allow_nan=False).encode('utf-8')
            self.send_response(status);self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)

        def do_GET(self):
            path=urlparse(self.path).path
            if path in ('/healthz','/health'):
                configured=all(os.environ.get(k) for k in ('FOUNDRY_ENDPOINT','FOUNDRY_API_KEY','FOUNDRY_DEPLOYMENT'))
                return self.send(200,dict(status='ok',version='integrated-room-v1',llm_configured=configured,
                    connectivity_verified=False,explanation_mode='verified-fact-selection'))
            if path=='/api/bootstrap':return self.send(200,app.bootstrap)
            files={'/':'index.html','/index.html':'index.html','/app.js':'app.js','/i18n.js':'i18n.js','/styles.css':'styles.css'}
            if path in files:
                mime='text/html' if path in ('/','/index.html') else 'text/css' if path.endswith('.css') else 'text/javascript'
                return self.send(200,(ROOT/'web/coach-room'/files[path]).read_bytes(),mime+'; charset=utf-8')
            self.send(404,{'error':'NOT_FOUND'})

        def do_POST(self):
            path=urlparse(self.path).path
            if path not in ('/api/evaluate','/api/explain'):return self.send(404,{'error':'NOT_FOUND'})
            origin=self.headers.get('Origin')
            if origin and urlparse(origin).netloc!=self.headers.get('Host'):return self.send(403,{'error':'CROSS_ORIGIN_DISABLED'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=8192:return self.send(413,{'error':'INVALID_BODY_SIZE'})
                cls=ExplainRequest if path=='/api/explain' else RoomRequest
                request=cls.model_validate_json(self.rfile.read(size))
                result=app.explanation(request) if path=='/api/explain' else app.snapshot(request)
                self.send(200,result)
            except (ValueError,KeyError,TypeError):self.send(400,{'error':'INVALID_REQUEST_OR_PLAN'})
            except TimeoutError:self.send(503,{'error':'EXPLANATION_BUSY'})
    return Handler


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=int(os.environ.get('PORT',8000)))
    args=parser.parse_args()
    bootstrap,evaluate=create_room();app=IntegratedApp(bootstrap,evaluate)
    print(f'Integrated coach room: http://{args.host}:{args.port} (English default, Hebrew supported)',flush=True)
    ThreadingHTTPServer((args.host,args.port),make_handler(app)).serve_forever()


if __name__=='__main__':main()
