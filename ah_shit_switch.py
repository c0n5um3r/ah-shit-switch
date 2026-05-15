#!/usr/bin/env python3

import evdev
import json
import logging
import selectors
import subprocess
import sys
import time
from evdev import InputDevice, ecodes

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    stream=sys.stderr,
)
log = logging.getLogger(__name__)

# fmt: off
CHARS = {
    'en': {
        ecodes.KEY_Q: ('q','Q'), ecodes.KEY_W: ('w','W'), ecodes.KEY_E: ('e','E'),
        ecodes.KEY_R: ('r','R'), ecodes.KEY_T: ('t','T'), ecodes.KEY_Y: ('y','Y'),
        ecodes.KEY_U: ('u','U'), ecodes.KEY_I: ('i','I'), ecodes.KEY_O: ('o','O'),
        ecodes.KEY_P: ('p','P'), ecodes.KEY_LEFTBRACE:  ('[','{'), ecodes.KEY_RIGHTBRACE: (']','}'),
        ecodes.KEY_A: ('a','A'), ecodes.KEY_S: ('s','S'), ecodes.KEY_D: ('d','D'),
        ecodes.KEY_F: ('f','F'), ecodes.KEY_G: ('g','G'), ecodes.KEY_H: ('h','H'),
        ecodes.KEY_J: ('j','J'), ecodes.KEY_K: ('k','K'), ecodes.KEY_L: ('l','L'),
        ecodes.KEY_SEMICOLON: (';',':'), ecodes.KEY_APOSTROPHE: ("'",'"'),
        ecodes.KEY_Z: ('z','Z'), ecodes.KEY_X: ('x','X'), ecodes.KEY_C: ('c','C'),
        ecodes.KEY_V: ('v','V'), ecodes.KEY_B: ('b','B'), ecodes.KEY_N: ('n','N'),
        ecodes.KEY_M: ('m','M'), ecodes.KEY_COMMA: (',','<'), ecodes.KEY_DOT: ('.', '>'),
        ecodes.KEY_SLASH: ('/','?'), ecodes.KEY_GRAVE: ('`','~'),
    },
    'ru': {
        ecodes.KEY_Q: ('й','Й'), ecodes.KEY_W: ('ц','Ц'), ecodes.KEY_E: ('у','У'),
        ecodes.KEY_R: ('к','К'), ecodes.KEY_T: ('е','Е'), ecodes.KEY_Y: ('н','Н'),
        ecodes.KEY_U: ('г','Г'), ecodes.KEY_I: ('ш','Ш'), ecodes.KEY_O: ('щ','Щ'),
        ecodes.KEY_P: ('з','З'), ecodes.KEY_LEFTBRACE:  ('х','Х'), ecodes.KEY_RIGHTBRACE: ('ъ','Ъ'),
        ecodes.KEY_A: ('ф','Ф'), ecodes.KEY_S: ('ы','Ы'), ecodes.KEY_D: ('в','В'),
        ecodes.KEY_F: ('а','А'), ecodes.KEY_G: ('п','П'), ecodes.KEY_H: ('р','Р'),
        ecodes.KEY_J: ('о','О'), ecodes.KEY_K: ('л','Л'), ecodes.KEY_L: ('д','Д'),
        ecodes.KEY_SEMICOLON: ('ж','Ж'), ecodes.KEY_APOSTROPHE: ('э','Э'),
        ecodes.KEY_Z: ('я','Я'), ecodes.KEY_X: ('ч','Ч'), ecodes.KEY_C: ('с','С'),
        ecodes.KEY_V: ('м','М'), ecodes.KEY_B: ('и','И'), ecodes.KEY_N: ('т','Т'),
        ecodes.KEY_M: ('ь','Ь'), ecodes.KEY_COMMA: ('б','Б'), ecodes.KEY_DOT: ('ю','Ю'),
        ecodes.KEY_SLASH: ('.', ','), ecodes.KEY_GRAVE: ('ё','Ё'),
    },
}
# fmt: on

ALL_KEYS  = set(CHARS['en'].keys())

SENT_BREAK = {
    ecodes.KEY_ENTER, ecodes.KEY_KPENTER,
    ecodes.KEY_TAB,   ecodes.KEY_ESC,
}

SENT_BREAK_CHARS = {'.'}

CTRL_KEYS  = {ecodes.KEY_LEFTCTRL,  ecodes.KEY_RIGHTCTRL}
ALT_KEYS   = {ecodes.KEY_LEFTALT,   ecodes.KEY_RIGHTALT}
SHIFT_KEYS = {ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT}
META_KEYS  = {ecodes.KEY_LEFTMETA,  ecodes.KEY_RIGHTMETA}
ALL_MODS   = CTRL_KEYS | ALT_KEYS | SHIFT_KEYS | META_KEYS | {ecodes.KEY_CAPSLOCK}

DOUBLE_TAP_MS = 0.5   # seconds


def get_layout() -> str:
    try:
        out = subprocess.run(
            ['hyprctl', 'devices', '-j'],
            capture_output=True, text=True, timeout=1.0, check=True,
        ).stdout
        for kb in json.loads(out).get('keyboards', []):
            if any(s in kb.get('name', '').lower() for s in ('virtual', 'uinput')):
                continue
            km = kb.get('active_keymap', '').lower()
            return 'ru' if ('russian' in km or km.startswith('ru')) else 'en'
    except Exception as exc:
        log.warning('layout detection failed: %s', exc)
    return 'en'


def decode(buf: list, layout: str) -> str:
    cm = CHARS[layout]
    parts = []
    for k, sh in buf:
        if k == ecodes.KEY_SPACE:
            parts.append(' ')
        elif k in cm:
            parts.append(cm[k][1 if sh else 0])
    return ''.join(parts)


def find_switch_start(buf: list, from_layout: str) -> int:
    """Index of first char to switch: after last . or , in the TARGET layout, or 0.

    We scan using the intended (target) layout because in the wrong layout
    punctuation keys map to letters — e.g. KEY_DOT in RU is 'ю', not '.'.
    """
    to_layout = 'ru' if from_layout == 'en' else 'en'
    cm = CHARS[to_layout]
    for i in range(len(buf) - 1, -1, -1):
        k, sh = buf[i]
        if k in cm and cm[k][1 if sh else 0] in SENT_BREAK_CHARS:
            return i + 1
    return 0


def do_switch(buf: list, layout: str) -> None:
    if not buf:
        return
    start     = find_switch_start(buf, layout)
    sub       = buf[start:]
    if not sub:
        return
    target    = 'ru' if layout == 'en' else 'en'
    corrected = decode(sub, target)
    if not corrected:
        return
    log.info('switch: %r → %r  (%s→%s)', decode(sub, layout), corrected, layout, target)
    time.sleep(0.05)
    args = ['wtype', '-d', '10']
    for _ in sub:
        args += ['-k', 'BackSpace']
    args += ['--', corrected]
    try:
        subprocess.run(args, timeout=5.0, check=True)
    except Exception as exc:
        log.error('wtype failed: %s', exc)


def find_keyboards() -> list:
    result = []
    for path in evdev.list_devices():
        try:
            dev  = InputDevice(path)
            caps = dev.capabilities()
            if ecodes.EV_KEY not in caps:
                continue
            keys = caps[ecodes.EV_KEY]
            if ecodes.KEY_A not in keys or ecodes.KEY_SPACE not in keys:
                continue
            name = dev.name.lower()
            if any(s in name for s in ('virtual', 'uinput')):
                continue
            log.info('keyboard: %s  %s', path, dev.name)
            result.append(dev)
        except Exception:
            pass
    return result


def run(keyboards: list) -> None:
    sel = selectors.DefaultSelector()
    for dev in keyboards:
        sel.register(dev, selectors.EVENT_READ)
    fd_map = {dev.fd: dev for dev in keyboards}

    buf   = []
    shift = False
    ctrl  = False
    alt   = False

    lshift_held        = False
    any_key_while_held = False
    lshift_tap_pending = None   # monotonic time of last clean tap, or None

    while True:
        for key, _ in sel.select(timeout=1.0):
            dev = fd_map[key.fd]
            try:
                events = dev.read()
            except OSError:
                log.warning('device disconnected: %s', dev.path)
                sel.unregister(dev)
                del fd_map[dev.fd]
                continue

            for ev in events:
                if ev.type != ecodes.EV_KEY:
                    continue

                code   = ev.code
                kstate = ev.value   # 0=up 1=down 2=repeat

                if code in SHIFT_KEYS:
                    shift = (kstate != 0)
                if code in CTRL_KEYS:
                    ctrl  = (kstate != 0)
                if code in ALT_KEYS:
                    alt   = (kstate != 0)

                if code == ecodes.KEY_LEFTSHIFT:
                    if kstate == 1:    # down
                        lshift_held        = True
                        any_key_while_held = False
                    elif kstate == 0:  # up
                        lshift_held = False
                        if not any_key_while_held:
                            now = time.monotonic()
                            if lshift_tap_pending is not None and now - lshift_tap_pending < DOUBLE_TAP_MS:
                                saved_buf    = list(buf)
                                saved_layout = get_layout()
                                buf.clear()
                                lshift_tap_pending = None
                                do_switch(saved_buf, saved_layout)
                            else:
                                lshift_tap_pending = now
                    continue

                if kstate == 0:
                    continue

                if lshift_held and code not in ALL_MODS:
                    any_key_while_held = True

                if kstate == 2:
                    continue

                if code in SENT_BREAK:
                    buf.clear()
                    lshift_tap_pending = None
                    continue

                if code == ecodes.KEY_BACKSPACE:
                    if buf:
                        buf.pop()
                    continue

                if code in ALL_MODS:
                    continue

                if ctrl or alt:
                    buf.clear()
                    lshift_tap_pending = None
                    continue

                lshift_tap_pending = None

                if code == ecodes.KEY_SPACE:
                    buf.append((ecodes.KEY_SPACE, False))
                elif code in ALL_KEYS:
                    buf.append((code, shift))


def main() -> None:
    log.info('ah-shit-switch starting')
    keyboards = find_keyboards()
    if not keyboards:
        log.error('no keyboards found — add yourself to the input group')
        sys.exit(1)
    try:
        run(keyboards)
    except KeyboardInterrupt:
        log.info('stopped')


if __name__ == '__main__':
    main()
