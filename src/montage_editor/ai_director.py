"""Optional local Ollama planning. Models propose bounded decisions, never commands."""
from dataclasses import replace
import json
import math
from urllib.error import URLError
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

DEFAULT_BRIEF = 'Cinematic Christian undertone: perseverance, reflection, hope in Christ. Build from restraint to energy. Use purposeful transitions.'
SCHEMA = {
    'type':'object', 'additionalProperties':False,
    'properties':{
        'candidate_order':{'type':'array','items':{'type':'integer'},'minItems':1,'maxItems':120},
        'minimum_clip':{'type':'number','minimum':.75,'maximum':6},
        'maximum_clip':{'type':'number','minimum':.75,'maximum':6},
        'transition':{'type':'string','enum':['cut','fade_black','fade_white','zoom','cinematic','push','zoom_blend','blur','dissolve']},
        'transition_duration':{'type':'number','minimum':.05,'maximum':1},
        'rationale':{'type':'string','maxLength':2000},
    },
    'required':['candidate_order','minimum_clip','maximum_clip','transition','transition_duration','rationale']
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('Ollama redirect refused; use the local service')


class OllamaDirector:
    def __init__(self, model, timeout=120):
        if not isinstance(model,str) or not model.strip() or len(model)>200:
            raise ValueError('Choose an installed Ollama model')
        self.model=model
        self.timeout=timeout

    def plan(self,candidates,brief=DEFAULT_BRIEF):
        candidates=sorted(candidates,key=lambda c:-c['score'])[:120]
        sources={path:i for i,path in enumerate(dict.fromkeys(c['source'] for c in candidates))}
        evidence=[{'id':i,'source_id':sources[c['source']], 'time':c['time'],
                   'activity':c['score'],'source_duration':c['source_duration']} for i,c in enumerate(candidates)]
        payload={'model':self.model,'stream':False,'format':SCHEMA,'options':{'temperature':.2,'num_predict':2048},
                 'messages':[{'role':'system','content':
                   'You direct local gaming edits. Use only supplied activity evidence, not imagined kills or visual content. '
                   'Rank candidate IDs in preferred priority order. The deterministic engine fits clips to a measured beat grid (or music attacks when no steady beat is found). '
                   'Choose global pacing and one supported transition; prefer cinematic, push or zoom_blend over repeated flashes. No commands, paths, invented media, quotations or effects. '
                   'Christian intent should express humility and hope, not equate in-game kills with divine approval. '
                   'Return only JSON matching this schema: '+json.dumps(SCHEMA)},
                   {'role':'user','content':json.dumps({'creative_brief':brief[:4000],'candidates':evidence})}]}
        request=Request('http://127.0.0.1:11434/api/chat',data=json.dumps(payload).encode(),
                        headers={'Content-Type':'application/json'},method='POST')
        try:
            # Loopback only; ignore proxy configuration and reject redirects.
            with build_opener(ProxyHandler({}),NoRedirect()).open(request,timeout=self.timeout) as response:
                raw=response.read(256000)
            result=json.loads(raw)
            if not result.get('done'):
                raise ValueError('Ollama response was incomplete')
            plan=json.loads(result['message']['content'])
        except (URLError,TimeoutError,OSError,KeyError,json.JSONDecodeError) as error:
            raise ValueError('Ollama planning failed. Start local Ollama, select an installed model, and retry. '+str(error)) from error
        return validate_plan(plan,len(candidates)),candidates


def validate_plan(plan,count):
    if not isinstance(plan,dict) or set(plan)!=set(SCHEMA['required']):
        raise ValueError('AI plan has missing or unsupported fields')
    order=plan['candidate_order']
    if not isinstance(order,list) or not order or len(order)>count:
        raise ValueError('AI candidate order is invalid')
    if any(type(i) is not int or not 0<=i<count for i in order) or len(set(order))!=len(order):
        raise ValueError('AI plan refers to invalid or duplicate candidates')
    for name,low,high in [('minimum_clip',.75,6),('maximum_clip',.75,6),('transition_duration',.05,1)]:
        value=plan[name]
        if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:
            raise ValueError('AI pacing is outside supported bounds')
    if plan['minimum_clip']>plan['maximum_clip'] or plan['transition'] not in ('cut','fade_black','fade_white','zoom','cinematic','push','zoom_blend','blur','dissolve'):
        raise ValueError('AI transition or pacing is invalid')
    if not isinstance(plan['rationale'],str) or len(plan['rationale'])>2000:
        raise ValueError('Invalid AI rationale')
    return plan


def configure_plan(plan,candidates,settings):
    validate_plan(plan,len(candidates))
    order=plan['candidate_order']+[i for i in range(len(candidates)) if i not in plan['candidate_order']]
    return [candidates[i] for i in order],replace(settings,minimum_clip=plan['minimum_clip'],maximum_clip=plan['maximum_clip'])
