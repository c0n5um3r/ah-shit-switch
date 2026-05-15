# ah-shit-switch

Punto Switcher для Hyprland/Wayland. Исправляет слово, набранное в неправильной раскладке, по двойному тапу левого Shift.

**Сделано под себя.** Работает — забирайте, переделывайте. Коммиты не принимаются.

---

## Как это работает

Демон читает события клавиатуры напрямую через `evdev` (не зависит от compositor), копит буфер нажатых клавиш. При двойном тапе левого Shift:

1. Спрашивает у Hyprland текущую раскладку через `hyprctl devices`
2. Декодирует буфер в противоположную раскладку
3. Отправляет N×Backspace + исправленное слово через `wtype`

**Триггер:** два последовательных тапа левого Shift без других клавиш между ними (≤ 500 мс). Shift+буква триггер не вызывает.

**Область переключения:** от последней `.` до курсора. Если точки нет — весь текст до начала сообщения. Граница ищется по **целевой** раскладке: в RU раскладке KEY_DOT это буква «ю», а не точка — ложных разрывов нет. Запятая намеренно не используется как граница: `?` в EN раскладке (KEY_SLASH+Shift) — это `,` в RU, что давало ложные срабатывания внутри фразы.

**Умная конвертация по словам:** буфер разбивается по пробелам, каждое слово оценивается независимо. Оценка считается как `частота букв × коэффициент чередования гласных/согласных`. Идея: настоящие слова чередуют гласные и согласные, а гибрид от не той раскладки — нет (например, `gbie` чередуется 1/3, `пишу` — 3/3). Дополнительно, если в исходном слове есть «нелетерные» символы (`[`, `]`, `{`, `}`, и т. п.) — это сильный признак того, что нажимались русские буквенные клавиши в EN-раскладке, и слово точно конвертится.

Слова, которые уже выглядят нормально в текущей раскладке (например, корректно набранное «меня»), не трогаются. Конвертируются только те, что в целевой раскладке выглядят осмысленнее (например, «ЩЫШТЕ» → «OSINT», `gbie` → `пишу`). Это позволяет в одном сообщении исправлять только реально неправильно набранные куски, не ломая остальное.

**Буфер сбрасывается** на Enter / Tab / Esc / любом Ctrl+X / Alt+X.

## Зависимости

- Python 3.10+
- [`python-evdev`](https://python-evdev.readthedocs.io/)
- [`wtype`](https://github.com/atx/wtype)
- `hyprctl` (из Hyprland)

```bash
sudo pacman -S python-evdev wtype
```

## Установка

```bash
git clone https://github.com/c0n5um3r/ah-shit-switch
cd ah-shit-switch
bash install.sh
```

Скрипт:
- Копирует демон в `/usr/local/bin/ah-shit-switch`
- Устанавливает systemd user unit
- Добавляет пользователя в группу `input` (если ещё не там)
- Включает и запускает сервис

После добавления в группу `input` нужен **повторный вход в сессию**.

## Управление

```bash
systemctl --user status ah-shit-switch
systemctl --user stop ah-shit-switch
systemctl --user restart ah-shit-switch
journalctl --user -u ah-shit-switch -f
```

## Ограничения

- Только Hyprland (layout detection через `hyprctl`)
- Раскладки: ru ↔ en (ЙЦУКЕН / QWERTY)
- Триггер срабатывает по текущей раскладке на момент нажатия. Переключите раскладку до двойного Shift, а не после.
- Устройства с доп. кнопками (игровые мыши), которые ОС видит как клавиатуру, тоже захватываются — в теории могут влиять на буфер.

---

# ah-shit-switch (English)

Punto Switcher equivalent for Hyprland/Wayland. Corrects a word typed in the wrong keyboard layout with a double-tap of the left Shift key.

**Built for personal use.** Take it, fork it, do what you want with it. Pull requests won't be accepted.

---

## How it works

The daemon reads raw keyboard events via `evdev` (compositor-independent) and maintains a buffer of keystrokes. On double left-Shift tap:

1. Queries the current layout from Hyprland via `hyprctl devices`
2. Decodes the buffer using the opposite layout's character map
3. Sends N×Backspace + the corrected word via `wtype`

**Trigger:** two consecutive left Shift taps with no other key in between (≤ 500 ms). Shift+letter does not trigger.

**Switch scope:** from the last `.` to the cursor. If none found — the entire text up to the start of the message. Boundary is detected using the **target** layout: in the RU layout KEY_DOT is the letter «ю», not a period — no false splits. Comma is intentionally excluded: `?` in the EN layout (KEY_SLASH+Shift) maps to `,` in RU, which caused false splits inside phrases.

**Per-word smart conversion:** the buffer is split by spaces and each word is judged independently. The score is `letter frequency × vowel/consonant alternation ratio`. The idea: real words alternate vowels and consonants; wrong-layout gibberish doesn't (e.g. `gbie` alternates 1/3, `пишу` alternates 3/3). Additionally, if the source decoding contains non-letter symbols (`[`, `]`, `{`, `}`, etc.), that's a strong signal that Russian letter keys were hit while in the EN layout — the word is forcibly converted.

Words that already look fine in the current layout (e.g. a correctly typed «меня») are left alone. Only words that look more meaningful in the target layout (e.g. «ЩЫШТЕ» → «OSINT», `gbie` → `пишу`) get converted. This lets you fix only the truly wrong fragments in a message without breaking the rest.

**Buffer resets** on Enter / Tab / Esc / any Ctrl+X / Alt+X.

## Dependencies

- Python 3.10+
- [`python-evdev`](https://python-evdev.readthedocs.io/)
- [`wtype`](https://github.com/atx/wtype)
- `hyprctl` (part of Hyprland)

```bash
sudo pacman -S python-evdev wtype
```

For non-Arch distros, install `python-evdev` via pip and `wtype` from your package manager or source.

## Installation

```bash
git clone https://github.com/c0n5um3r/ah-shit-switch
cd ah-shit-switch
bash install.sh
```

The script:
- Copies the daemon to `/usr/local/bin/ah-shit-switch`
- Installs a systemd user unit
- Adds the current user to the `input` group if needed
- Enables and starts the service

If you were added to the `input` group, **log out and back in** before testing.

## Service management

```bash
systemctl --user status ah-shit-switch
systemctl --user stop ah-shit-switch
systemctl --user restart ah-shit-switch
journalctl --user -u ah-shit-switch -f
```

## Limitations

- Hyprland only (layout detection uses `hyprctl`)
- Layouts: ru ↔ en (ЙЦУКЕН / QWERTY)
- Layout is queried at trigger time — switch layout *before* the double Shift, not after
- Gaming mice or other devices the OS exposes as keyboards are also picked up and may theoretically affect the buffer
