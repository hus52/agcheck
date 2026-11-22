# AgCheck

AgCheck is a tiny, read-only Windows diagnostic. It looks at the window you
currently have in focus and tells you **whether the text in it can be reached by
an assistive-technology layer** — the same layer screen readers and automation
tools rely on.

It answers one question: *how does this window expose its text?*

- **A Java application** — readable through the Java Access Bridge.
- **An ordinary Windows text control** — readable directly (Win32).
- **Neither** — a browser, an Electron app or a custom-drawn editor. Reading its
  text needs Windows UI Automation.

## What it does and does not do

- It **never types and never clicks**. It only inspects.
- It **never records the actual text**. The result file shows only the *shape* of
  what it found — letters become `a`/`A`, digits become `9`. So "Hello 42" is
  written as `Aaaaa 99`. The result is safe to share.
- It writes a plain-text file `agcheck-<date>.txt` next to the program (or in your
  Documents folder if it can't write beside itself).

## How to run it

1. Download `AgCheck.exe` from the [Releases](https://github.com/hus52/agcheck/releases) page.
2. Click the window you want to check so it has focus and shows a line of text.
3. Run `AgCheck.exe`, press **Check now**, then **Open result**.

See [`AgCheck/HOW TO USE.txt`](AgCheck/HOW%20TO%20USE.txt) for the same steps in
plain language.

`WindowsAccessBridge-64.dll` (Oracle's redistributable Java Access Bridge) ships
beside the exe as a fallback for Java apps whose own copy isn't found.

## The three verdicts

| Verdict | Meaning |
|---|---|
| **Java window** | Its text and cursor are readable through the Java Access Bridge. |
| **Ordinary Windows text control** | Its text is readable directly (Win32). |
| **Needs UI Automation** | Not Java, and no standard control returned text. |

## Build

AgCheck is a single Python file. To build the exe yourself, from the `src`
folder:

```
python -m PyInstaller --onefile --windowed --name AgCheck --distpath dist --workpath build --specpath build --noconfirm --exclude-module numpy --exclude-module PIL --exclude-module pandas agcheck.py
```

The exe appears in `src/dist/AgCheck.exe`. Copy it next to
`WindowsAccessBridge-64.dll` (the `AgCheck/` folder) to run it.

Self-check: `python src/agcheck.py --selftest`.

## Licence

MIT — see [LICENSE](LICENSE). Release builds are code-signed through the
[SignPath Foundation](https://signpath.org) OSS program (once set up); until then
an unsigned build may show an "unknown publisher" warning.
