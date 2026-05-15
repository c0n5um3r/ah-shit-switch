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

# Approximate letter frequencies — used to score "wordiness" per language.
RU_FREQ = {
    'о':0.108, 'е':0.085, 'а':0.080, 'и':0.073, 'н':0.067, 'т':0.063,
    'с':0.055, 'р':0.047, 'в':0.045, 'л':0.044, 'к':0.035, 'м':0.032,
    'д':0.030, 'п':0.028, 'у':0.026, 'я':0.020, 'ы':0.019, 'ь':0.017,
    'г':0.017, 'з':0.016, 'б':0.015, 'ч':0.013, 'й':0.012, 'х':0.009,
    'ж':0.009, 'ш':0.007, 'ю':0.006, 'ц':0.004, 'щ':0.003, 'э':0.003,
    'ф':0.002, 'ё':0.001, 'ъ':0.0004,
}
EN_FREQ = {
    'e':0.127, 't':0.091, 'a':0.082, 'o':0.075, 'i':0.070, 'n':0.067,
    's':0.063, 'h':0.061, 'r':0.060, 'd':0.043, 'l':0.040, 'c':0.028,
    'u':0.028, 'm':0.024, 'w':0.024, 'f':0.022, 'g':0.020, 'y':0.020,
    'p':0.019, 'b':0.015, 'v':0.010, 'k':0.008, 'j':0.002, 'x':0.002,
    'q':0.001, 'z':0.001,
}

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


# Chars that come from RU letter keys when typed in EN layout —
# strong signal that the layout was wrong.
SPECIAL_CHARS = set("[]{}`~|\\")
TRAILING_PUNCT = set('.,!?;:')

RU_VOWELS = set('аеёиоуыэюя')
EN_VOWELS = set('aeiouy')  # y as vowel for transition counting


def strip_trailing(text: str) -> str:
    while text and text[-1] in TRAILING_PUNCT:
        text = text[:-1]
    return text


def has_special(text: str) -> bool:
    return any(c in SPECIAL_CHARS for c in text)


def transition_ratio(text: str, lang: str) -> float:
    """Vowel<->consonant alternation ratio. Real words alternate; gibberish doesn't."""
    vowels = RU_VOWELS if lang == 'ru' else EN_VOWELS
    skip   = set('ьъ') if lang == 'ru' else set()
    letters = [c.lower() for c in text if c.isalpha() and c.lower() not in skip]
    if len(letters) < 2:
        return 1.0
    trans = sum(1 for i in range(len(letters) - 1)
                if (letters[i] in vowels) != (letters[i+1] in vowels))
    return trans / (len(letters) - 1)


def quality_score(text: str, lang: str) -> float:
    """Letter frequency × (0.2 + 0.8 × alternation). Penalises non-alternating gibberish."""
    freq = RU_FREQ if lang == 'ru' else EN_FREQ
    freq_sum = sum(freq.get(c.lower(), 0) for c in text)
    return freq_sum * (0.2 + 0.8 * transition_ratio(text, lang))


def split_words(buf: list) -> list:
    """Split buffer into chunks: (is_space, sub_buf)."""
    out, cur = [], []
    for k, sh in buf:
        if k == ecodes.KEY_SPACE:
            if cur:
                out.append((False, cur))
                cur = []
            out.append((True, [(k, sh)]))
        else:
            cur.append((k, sh))
    if cur:
        out.append((False, cur))
    return out


def should_convert(chunk: list, from_layout: str) -> bool:
    to_layout = 'ru' if from_layout == 'en' else 'en'
    src = decode(chunk, from_layout)
    tgt = decode(chunk, to_layout)
    src_core = strip_trailing(src)

    # Special chars in source (RU letter keys hit while in EN layout) → wrong layout
    if has_special(src_core):
        return True

    return quality_score(tgt, to_layout) > quality_score(src, from_layout)


def smart_convert(buf: list, from_layout: str) -> str:
    """Per-word smart conversion. Keep words that already look correct in source layout."""
    to_layout = 'ru' if from_layout == 'en' else 'en'
    parts = []
    for is_space, chunk in split_words(buf):
        if is_space:
            parts.append(' ')
            continue
        if should_convert(chunk, from_layout):
            parts.append(decode(chunk, to_layout))
        else:
            parts.append(decode(chunk, from_layout))
    return ''.join(parts)


def do_switch(buf: list, layout: str) -> None:
    if not buf:
        return
    start = find_switch_start(buf, layout)
    sub   = buf[start:]
    if not sub:
        return
    visible  = decode(sub, layout)
    new_text = smart_convert(sub, layout)
    if new_text == visible:
        log.info('no conversion needed for %r', visible)
        return
    log.info('switch: %r → %r  (from %s)', visible, new_text, layout)
    time.sleep(0.05)
    args = ['wtype', '-d', '10']
    for _ in range(len(visible)):
        args += ['-k', 'BackSpace']
    args += ['--', new_text]
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
