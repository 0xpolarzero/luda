"""Raw PTY oracle: records bytes/signals, never interprets input as commands."""
import json
import os
from pathlib import Path
import select
import signal
import sys
import termios
import tty

path = Path(sys.argv[1])
bracketed = sys.argv[2] == 'bracketed'
previous = termios.tcgetattr(0)
tty.setraw(0)
settings = termios.tcgetattr(0)
settings[3] |= termios.ISIG
termios.tcsetattr(0, termios.TCSANOW, settings)
state = {'hex': '', 'interrupts': 0, 'ready': True, 'bracketed': bracketed}
def save():
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state))
    temporary.replace(path)
def interrupted(signum, frame):
    state['interrupts'] += 1
    save()
signal.signal(signal.SIGINT, interrupted)
os.write(1, b'\x1b[?2004h' if bracketed else b'\x1b[?2004l')
save()
try:
    while True:
        if select.select([0], [], [], .2)[0]:
            data = os.read(0, 65536)
            if not data:
                break
            state['hex'] += data.hex()
            save()
finally:
    termios.tcsetattr(0, termios.TCSANOW, previous)
