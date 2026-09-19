"""Records terminal input without ever executing it."""
import json
import os
from pathlib import Path
import sys
p=Path(sys.argv[1]);value=b'';p.write_text(json.dumps({'text':''}))
while True:
 data=os.read(0,4096)
 if not data:break
 value+=data
 tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps({'text':value.decode('utf-8','replace')},ensure_ascii=False));tmp.replace(p)
