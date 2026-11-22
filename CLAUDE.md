# AgCheck - notes for future sessions

AgCheck is a small, read-only Windows diagnostic. Given the window currently in
focus, it reports **how that window exposes its text**: Java Access Bridge, an
ordinary Win32 text control, or neither (needs UI Automation).

**Keep this repo generic and clean.** It is public and open-source so it can get
free code signing. Do **not** add anything about who uses it or why - no clinical
/ medical / patient / reporting / dictation references, no named target
application. It is simply a text-reachability checker.

## How it behaves
- Never types, never clicks. Inspection only.
- Never records actual text - only the *shape* (letters -> a/A, digits -> 9).
- Writes `agcheck-<date>.txt` next to the exe, or in Documents as a fallback.
- `WindowsAccessBridge-64.dll` ships beside the exe (Oracle redistributable)
  as a fallback for Java apps whose own copy isn't found.

## Build / check
- Source: single file `src/agcheck.py`.
- Self-check: `python src/agcheck.py --selftest`; lint: `python -m pyflakes src/agcheck.py`.
- Build (from `src`):
  `python -m PyInstaller --onefile --windowed --name AgCheck --distpath dist --workpath build --specpath build --noconfirm --exclude-module numpy --exclude-module PIL --exclude-module pandas agcheck.py`
  then copy `src/dist/AgCheck.exe` into `AgCheck/`.
- The exe is git-ignored; it ships only as a GitHub release asset.

## Signing plan
- Target machine runs stock Windows Defender, which deletes unsigned PyInstaller
  exes as a false positive. Fix = code signing.
- Plan: SignPath Foundation OSS program (https://signpath.org) - free signing for
  open-source projects. Review is not instant.
- Interim for testing: the machine's managing company can add a Defender folder
  exclusion, or report the file to Microsoft as a false positive
  (https://www.microsoft.com/wdsi/filesubmission). Do not evade detection by any
  other route.
