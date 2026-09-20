"""Passive terminal receiver: input is data, never commands; no expected payload."""
import json,os,select,sys,termios,tty
from pathlib import Path
out=Path(sys.argv[1]);previous=termios.tcgetattr(0);tty.setraw(0)
state={'hex':'','reads':0,'ready':True}
def publish():
    temporary=out/'received.tmp';temporary.write_text(json.dumps(state));temporary.replace(out/'received.json')
    value=bytes.fromhex(state['hex']).decode('utf-8',errors='replace').replace('\r','\n')
    text='Delivery receiver (data only; no shell)\r\nReceived bytes: '+str(len(bytes.fromhex(state['hex'])))+'\r\nUTF-8 receipt JSON (terminal CR rendered as LF):\r\n'+json.dumps(value,ensure_ascii=False)+'\r\n'
    os.write(1,b'\x1b[2J\x1b[H'+text.encode())
os.write(1,b'\x1b[?2004l');publish()
try:
    while True:
        if select.select([0],[],[],.2)[0]:
            data=os.read(0,65536)
            if not data:break
            state['hex']+=data.hex();state['reads']+=1;publish()
finally:termios.tcsetattr(0,termios.TCSANOW,previous)
