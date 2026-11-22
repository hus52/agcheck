"""AgCheck: can an assistive-technology tool read the text in the window you have focused?

READ ONLY. It never clicks, types or changes anything. Focus a window with some text in it and press "Check now".
It reports what kind of window it is and whether its text and cursor can be read - never the text itself, only its
"shape" (letters as a/A, digits as 9, punctuation and line breaks kept), so the output is safe to share.

Three outcomes: a Java application (readable through the Java Access Bridge), an ordinary Windows text control
(readable directly), or neither (a browser, an Electron app or a custom editor - reading it needs UI Automation).

MIT licensed. See README.md.
"""

from __future__ import annotations

import ctypes
import datetime as dt
import glob
import os
import platform
import sys
import time
from ctypes import wintypes
from pathlib import Path

APP, VERSION = "AgCheck", "1"
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
try:
    ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
except Exception:
    pass
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


# ---------------------------------------------------------------- Windows helpers

def title(h) -> str:
    n = user32.GetWindowTextLengthW(h)
    b = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(h, b, n + 1)
    return b.value


def class_name(h) -> str:
    b = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(h, b, 256)
    return b.value


def pid_of(h) -> int:
    p = wintypes.DWORD()
    user32.GetWindowThreadProcessId(h, ctypes.byref(p))
    return p.value


def exe_of(pid) -> tuple[str, str]:
    h = kernel32.OpenProcess(0x1000, False, pid)
    if not h:
        return "?", "?"
    try:
        b = ctypes.create_unicode_buffer(1024)
        n = wintypes.DWORD(1024)
        path = b.value if kernel32.QueryFullProcessImageNameW(h, 0, b, ctypes.byref(n)) else "?"
        wow = wintypes.BOOL()
        bits = ("32-bit" if wow.value else "64-bit") if kernel32.IsWow64Process(h, ctypes.byref(wow)) else "?"
        return path, bits
    finally:
        kernel32.CloseHandle(h)


class GUIThreadInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD), ("hwndActive", wintypes.HWND),
                ("hwndFocus", wintypes.HWND), ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
                ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND), ("rcCaret", wintypes.RECT)]


def focused() -> tuple[int, int]:
    """(foreground window, the control with the keyboard focus inside it)."""
    fg = user32.GetForegroundWindow()
    gti = GUIThreadInfo()
    gti.cbSize = ctypes.sizeof(gti)
    tid = user32.GetWindowThreadProcessId(fg, None)
    foc = gti.hwndFocus if user32.GetGUIThreadInfo(tid, ctypes.byref(gti)) else 0
    return fg, (foc or fg)


def class_chain(h) -> list[str]:
    out = []
    for _ in range(12):
        if not h:
            break
        out.append(class_name(h))
        h = user32.GetParent(h)
    return out


def win32_text(h) -> str | None:
    """Text of a standard Windows control via WM_GETTEXT (the system marshals it cross-process for real controls).
    None if the control returns nothing - normal for custom controls that draw their own text."""
    n = user32.SendMessageW(h, 0x000E, 0, 0)  # WM_GETTEXTLENGTH
    if n <= 0:
        return None
    b = ctypes.create_unicode_buffer(n + 1)
    user32.SendMessageW(h, 0x000D, n + 1, b)  # WM_GETTEXT
    return b.value or None


def shape(s: str) -> str:
    """The text's layout without its contents: letters -> a/A, digits -> 9, punctuation and line breaks kept."""
    out = []
    for ch in s:
        out.append("9" if ch.isdigit() else ("A" if ch.isupper() else "a") if ch.isalpha()
                   else "\u00b6\n" if ch == "\n" else "<CR>" if ch == "\r" else "<TAB>" if ch == "\t"
                   else ch if ch.isprintable() else f"<{ord(ch):02x}>")
    return "".join(out)


# ---------------------------------------------------------------- Java Access Bridge (only if the window is Java)

JOBJ, VMID = ctypes.c_int64, ctypes.c_long


class ContextInfo(ctypes.Structure):
    _fields_ = [("name", ctypes.c_wchar * 1024), ("description", ctypes.c_wchar * 1024),
                ("role", ctypes.c_wchar * 256), ("role_en_US", ctypes.c_wchar * 256),
                ("states", ctypes.c_wchar * 256), ("states_en_US", ctypes.c_wchar * 256),
                ("indexInParent", ctypes.c_int), ("childrenCount", ctypes.c_int),
                ("x", ctypes.c_int), ("y", ctypes.c_int), ("width", ctypes.c_int), ("height", ctypes.c_int),
                ("accessibleComponent", ctypes.c_int), ("accessibleAction", ctypes.c_int),
                ("accessibleSelection", ctypes.c_int), ("accessibleText", ctypes.c_int),
                ("accessibleInterfaces", ctypes.c_int)]


class TextInfo(ctypes.Structure):
    _fields_ = [("charCount", ctypes.c_int), ("caretIndex", ctypes.c_int), ("indexAtPoint", ctypes.c_int)]


def bridge_dlls() -> list[str]:
    here = Path(sys.executable if getattr(sys, "frozen", False) else __file__).parent
    places = glob.glob(r"C:\Program Files\*\*\bin\WindowsAccessBridge-64.dll")
    places += glob.glob(r"C:\Program Files\*\bin\WindowsAccessBridge-64.dll")
    places += glob.glob(r"C:\Program Files (x86)\*\*\bin\WindowsAccessBridge-64.dll")
    places += [os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsAccessBridge-64.dll"),
               str(here / "WindowsAccessBridge-64.dll")]
    seen = []
    for p in places:
        if os.path.exists(p) and p.lower() not in (s.lower() for s in seen):
            seen.append(p)
    return seen


class Bridge:
    def __init__(self, path):
        d = ctypes.CDLL(path)

        def sig(name, args, res=wintypes.BOOL):
            f = getattr(d, name)
            f.argtypes, f.restype = args, res

        d.Windows_run.restype = None
        sig("isJavaWindow", [wintypes.HWND])
        sig("getAccessibleContextFromHWND", [wintypes.HWND, ctypes.POINTER(VMID), ctypes.POINTER(JOBJ)])
        sig("getAccessibleContextInfo", [VMID, JOBJ, ctypes.POINTER(ContextInfo)])
        sig("getAccessibleChildFromContext", [VMID, JOBJ, ctypes.c_int], JOBJ)
        sig("releaseJavaObject", [VMID, JOBJ], None)
        sig("getAccessibleTextInfo", [VMID, JOBJ, ctypes.POINTER(TextInfo), ctypes.c_int, ctypes.c_int])
        sig("getAccessibleTextRange", [VMID, JOBJ, ctypes.c_int, ctypes.c_int, ctypes.c_wchar_p, ctypes.c_short])
        self.d = d
        d.Windows_run()
        self._pump(1.5)

    def _pump(self, secs):
        msg = wintypes.MSG()
        end = time.time() + secs
        while time.time() < end:
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.01)

    def is_java(self, h) -> bool:
        return bool(self.d.isJavaWindow(h))

    def root(self, h):
        vm, ac = VMID(), JOBJ()
        return (vm.value, ac.value) if self.d.getAccessibleContextFromHWND(h, ctypes.byref(vm), ctypes.byref(ac)) else None

    def info(self, vm, ac):
        i = ContextInfo()
        return i if self.d.getAccessibleContextInfo(vm, ac, ctypes.byref(i)) else None

    def text(self, vm, ac) -> tuple[int, int, str] | None:
        t = TextInfo()
        if not self.d.getAccessibleTextInfo(vm, ac, ctypes.byref(t), 0, 0):
            return None
        if t.charCount <= 0:
            return 0, t.caretIndex, ""
        cap = min(t.charCount, 3000)
        b = ctypes.create_unicode_buffer(cap + 2)
        self.d.getAccessibleTextRange(vm, ac, 0, cap - 1, b, cap + 1)
        return t.charCount, t.caretIndex, b.value


def editable_text_boxes(bridge, h):
    """Editable multi-line text fields in a Java window, biggest first. Returns [(vm, ac, info)]."""
    root = bridge.root(h)
    if not root:
        return []
    vm, ac = root
    boxes, stack, n = [], [(ac,)], 0
    while stack and n < 8000:
        (obj,) = stack.pop()
        i = bridge.info(vm, obj)
        if not i:
            continue
        n += 1
        st = i.states_en_US
        if i.role_en_US == "text" and "editable" in st and ("multiple line" in st or "multi_line" in st):
            boxes.append((vm, obj, i))
        for k in range(min(i.childrenCount, 400)):
            c = bridge.d.getAccessibleChildFromContext(vm, obj, k)
            if c:
                stack.append((c,))
    boxes.sort(key=lambda b: b[2].width * b[2].height, reverse=True)
    return boxes


# ---------------------------------------------------------------- the check

BRIDGE = None


def check() -> str:
    now = dt.datetime.now()
    r = [f"===== {APP} v{VERSION} - {now:%d %b %Y %H:%M:%S} =====",
         f"Windows: {platform.platform()} | this program: {8 * ctypes.sizeof(ctypes.c_void_p)}-bit"]
    fg, foc = focused()
    if not fg:
        r.append("No window is in front. Click into the text field you want to check, then press Check now.")
        return "\n".join(r)
    exe, bits = exe_of(pid_of(fg))
    r.append("")
    r.append(f"Window in front: shape {shape(title(fg)[:90])!r}  (class {class_name(fg)})")
    r.append(f"  program: {exe} ({bits})")
    r.append(f"Focused control: class {class_name(foc)!r}")
    r.append(f"  class chain (control -> window): {' < '.join(class_chain(foc))}")

    # 1) Java?
    global BRIDGE
    if BRIDGE is None:
        for p in bridge_dlls():
            try:
                BRIDGE = Bridge(p)
                r.append(f"Java Access Bridge loaded from: {p}")
                break
            except OSError as e:
                r.append(f"  could not load {p}: {e}")
    is_java = bool(BRIDGE and BRIDGE.is_java(fg))
    r.append(f"Is this a Java window (Access Bridge sees it)? {'YES' if is_java else 'no'}")

    if is_java:
        boxes = editable_text_boxes(BRIDGE, fg)
        r.append(f"  editable multi-line text fields found: {len(boxes)}")
        for n, (vm, ac, i) in enumerate(boxes[:3], 1):
            t = BRIDGE.text(vm, ac)
            r.append(f"  field {n}: ({i.x},{i.y} {i.width}x{i.height}) [{i.states_en_US}]")
            if t:
                chars, caret, sample = t
                r.append(f"    characters: {chars} | caret at: {caret} | text readable: {'yes' if chars >= 0 else 'no'}")
                if sample:
                    r.append("    shape (contents never shown):")
                    r += ["      | " + ln for ln in shape(sample[:600]).split("\n")]
            else:
                r.append("    text not readable through the bridge")
        r.append("")
        r.append("VERDICT: Java window - its text and cursor are readable through the Java Access Bridge."
                 if boxes else
                 "VERDICT: Java window, but no editable multi-line text field was found on this screen. Click into "
                 "the field you want to check and run Check now again.")
        return "\n".join(r)

    # 2) ordinary Windows control? Trust the text only if the focus is a real CHILD control, not the top window
    # (for a top-level window WM_GETTEXT returns the title bar, not the field - common for browser/Electron apps).
    child = foc != fg
    cls = class_name(foc).lower()
    looks_edit = any(k in cls for k in ("edit", "richedit", "scintilla", "textbox"))
    txt = win32_text(foc) if child else None
    r.append("")
    r.append("Keyboard focus is on a separate control inside the window." if child else
             "Keyboard focus is on the top window itself (no separate text control).")
    if child and txt is not None:
        r.append(f"That control returns text ({len(txt)} characters) to a standard Windows read.")
        r.append("  shape (contents never shown):")
        r += ["  | " + ln for ln in shape(txt[:600]).split("\n")]
        r.append("VERDICT: an ordinary Windows text control - its text is readable directly (Win32).")
    elif child and looks_edit:
        r.append("VERDICT: the control looks like a standard edit box but returned no text - it may be empty. Put a "
                 "line of text in the field and run Check now again.")
    else:
        r.append("VERDICT: not Java, and no readable standard Windows text control (likely a browser, an Electron app "
                 "or a custom-drawn editor). Reading it needs Windows UI Automation.")
    return "\n".join(r)


# ---------------------------------------------------------------- report file and window

def report_path() -> Path:
    here = Path(sys.executable if getattr(sys, "frozen", False) else __file__).parent
    name = f"agcheck-{dt.datetime.now():%Y%m%d}.txt"
    for folder in (here, Path.home() / "Documents", Path.home()):
        try:
            with open(folder / name, "a", encoding="utf-8"):
                pass
            return folder / name
        except OSError:
            continue
    return here / name


def save(section: str) -> Path:
    p = report_path()
    with open(p, "a", encoding="utf-8") as f:
        f.write(section + "\n\n")
    return p


def gui():
    import tkinter as tk
    from tkinter import scrolledtext
    root = tk.Tk()
    root.title(APP)
    root.geometry("860x600")
    root.attributes("-topmost", True)
    tk.Label(root, justify="left", anchor="w", padx=10, pady=8, text=(
        "AgCheck looks at the window you have focused and reports whether its text can be read by an "
        "assistive-technology tool. It never clicks or types, and never records the actual text (only its shape).\n"
        "1. Click into the text field you want to check (put a line of text in it first).\n"
        "2. Press 'Check now'.\n"
        "3. Press 'Open result' to see the saved file.")).pack(fill="x")
    bar = tk.Frame(root)
    bar.pack(fill="x", padx=10)
    out = scrolledtext.ScrolledText(root, wrap="none", font=("Consolas", 9))
    out.pack(fill="both", expand=True, padx=10, pady=8)

    def do_check():
        out.insert("end", "Checking the window in front...\n")
        root.update()
        try:
            section = check()
        except Exception:
            import traceback
            section = "Check failed:\n" + traceback.format_exc()
        p = save(section)
        out.insert("end", section + f"\n(Saved to {p})\n\n")
        out.see("end")

    tk.Button(bar, text="Check now", command=do_check, width=16).pack(side="left")
    tk.Button(bar, text="Open result", width=14,
              command=lambda: os.startfile(report_path()) if report_path().exists() else None).pack(side="left", padx=6)
    root.mainloop()


def _selftest():
    assert shape("Ab 9\tZ") == "Aa 9<TAB>A"
    assert shape("x1\n") == "a9\u00b6\n"
    assert shape("don't") == "aaa'a"  # punctuation kept, letters hidden
    assert "\n" in shape("a\nb") and shape("") == ""
    print("AgCheck self-check OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    elif "--cli" in sys.argv:
        print(check())
    else:
        gui()
