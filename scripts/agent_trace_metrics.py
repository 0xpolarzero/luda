"""Read-only accounting of existing Codex JSON events; never reruns an agent."""
import argparse
import base64
from collections import Counter
import json
from pathlib import Path


def metrics(events):
    calls=[e['item'] for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='mcp_tool_call']
    counts=Counter();elapsed=[];missing=[];volumes={};inspections=[]
    for call in calls:
        tool=call.get('tool');counts[tool]+=1
        volume=volumes.setdefault(tool,{'text_utf8_bytes':0,'images':0,'image_base64_characters':0,'decoded_image_bytes':0})
        payload=None
        for content in (call.get('result') or {}).get('content',[]):
            if content.get('type')=='text':
                text=content.get('text','');volume['text_utf8_bytes']+=len(text.encode())
                try:value=json.loads(text)
                except (ValueError,TypeError):continue
                if isinstance(value,dict) and payload is None:payload=value
            elif content.get('type')=='image':
                data=content.get('data','');volume['images']+=1;volume['image_base64_characters']+=len(data)
                volume['decoded_image_bytes']+=len(base64.b64decode(data,validate=True))
        if payload is not None and isinstance(payload.get('elapsed_ms'),(int,float)):elapsed.append(payload['elapsed_ms'])
        else:missing.append({'id':call.get('id'),'tool':tool})
        if tool=='desktop_inspect':
            nodes=(payload or {}).get('nodes',[])
            inspections.append({'id':call.get('id'),'arguments':call.get('arguments'),'ok':(payload or {}).get('ok'),'nodes':len(nodes),'showing_nodes':sum('showing' in n.get('states',[]) for n in nodes),'unnamed_nodes':sum(not n.get('name') for n in nodes),'text_utf8_bytes':sum(len(c.get('text','').encode()) for c in (call.get('result') or {}).get('content',[]) if c.get('type')=='text'),'truncated':(payload or {}).get('truncated')})
    return {'completed_calls':len(calls),'per_tool_calls':dict(counts),'reported_backend_elapsed_ms_sum':sum(elapsed),'calls_with_backend_elapsed_ms':len(elapsed),'calls_without_backend_elapsed_ms':missing,'timing_scope':'Sum of public elapsed_ms only; excludes model reasoning, MCP transport overhead and calls without timing. Full tool wall time unavailable without event timestamps.','response_content_volumes':volumes,'inspections':inspections,'volume_scope':'UTF-8 text and encoded/decoded image content bytes; not model-token counts or estimates of visual-token processing.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('events',type=Path);args=parser.parse_args()
    print(json.dumps(metrics([json.loads(line) for line in args.events.read_text().splitlines()]),indent=2,ensure_ascii=False))
