"""Real curses alternate-screen application; consumes text, never executes it."""
import curses
import json
import os
from pathlib import Path
import re
import select
import sys
import termios
import time
import tty

out = Path(sys.argv[1])
state = {'selected': 0, 'field': '', 'focus': 'menu', 'commits': 0, 'phase': 'starting'}
def save():
    (out / 'state.tmp').write_text(json.dumps(state))
    (out / 'state.tmp').replace(out / 'state.json')
def alternate_mode():
    old = termios.tcgetattr(0)
    try:
        tty.setraw(0)
        os.write(1, b'\x1b[?1049$p')
        reply = b''
        end = time.monotonic() + 1
        while time.monotonic() < end:
            if select.select([0], [], [], .05)[0]:
                reply += os.read(0, 128)
                match = re.search(rb'\x1b\[\?1049;([0-4])\$y', reply)
                if match:
                    return int(match[1])
        return None
    finally:
        termios.tcsetattr(0, termios.TCSANOW, old)

def app(screen):
    screen.keypad(True)
    state.update(phase='tui', mode_inside=alternate_mode())
    save()
    while True:
        screen.erase()
        screen.addstr(0, 0, 'Luda real curses application')
        screen.addstr(2, 0, 'Arrows: menu | Tab: next field | Enter: confirm | Esc: exit')
        for index, name in enumerate(('Alpha', 'Beta', 'Gamma')):
            screen.addstr(4 + index, 0, ('> ' if index == state['selected'] else '  ') + name)
        screen.addstr(8, 0, 'Text: ' + state['field'])
        screen.addstr(10, 0, 'Confirm selection and text')
        screen.addstr(12, 0, 'Focus: ' + state['focus'] + ' | Commits: ' + str(state['commits']))
        screen.refresh()
        key = screen.get_wch()
        if key == '\x1b':
            break
        if key == '\t':
            modes = ['menu', 'field', 'confirm']
            state['focus'] = modes[(modes.index(state['focus']) + 1) % 3]
        elif state['focus'] == 'menu' and key in (curses.KEY_DOWN, curses.KEY_UP):
            state['selected'] = (state['selected'] + (1 if key == curses.KEY_DOWN else -1)) % 3
        elif state['focus'] == 'field' and isinstance(key, str) and key.isprintable():
            state['field'] += key
        elif state['focus'] == 'confirm' and key in ('\n', '\r', curses.KEY_ENTER):
            state['commits'] += 1
            state['committed'] = {'selected': state['selected'], 'text': state['field']}
        save()

print('ORIGINAL TERMINAL SESSION - owned passive fixture', flush=True)
state['mode_before'] = alternate_mode()
curses.wrapper(app)
state.update(phase='restored', mode_after=alternate_mode())
save()
print('\nORIGINAL TERMINAL SESSION RESTORED - type q to finish', flush=True)
old = termios.tcgetattr(0)
try:
    tty.setraw(0)
    while os.read(0, 1) != b'q':
        pass
finally:
    termios.tcsetattr(0, termios.TCSANOW, old)
state['phase'] = 'finished'
save()
