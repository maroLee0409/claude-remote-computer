# claude-remote-computer

Let Claude Code see your screen and use your computer.

Some things have no API. A shop-floor MES built in JDeveloper. A WinForms tool from 2009.
An installer wizard. Device Manager. Claude takes a screenshot, **looks at it**, then moves
the mouse and types — the same way you would.

And when something on your PC is broken and you don't know why, it can go look: read the
error dialog, open Event Viewer, check Task Manager, and tell you what it found.

Remote servers over RDP work the same way. That's one more target, not a separate mode.

```
capture  ->  look at the image  ->  click / type  ->  capture again to verify
```

No browser extension. No admin rights. **Pillow is the only dependency** - everything else is
`ctypes` against `user32`/`kernel32`.

---

## Install

**As a plugin**

```
/plugin marketplace add maroLee0409/claude-remote-computer
/plugin install claude-remote-computer
```

**Or copy the skill**

```powershell
git clone https://github.com/maroLee0409/claude-remote-computer.git
cd claude-remote-computer
.\scripts\install.ps1        # copies skills/ into ~/.claude/skills/
```

```bash
pip install pillow           # the only dependency
```

Then just ask, in whatever words you'd use:

> "Open the MES app and pull up today's production numbers."
> "Something's wrong with my PC and I can't tell what — go look."
> "This installer is stuck on a dialog. Read it and get past it."
> "RDP into the server and tell me why the app pool keeps dying."

---

## Two ways it gets used

**Driving apps that have no API.** Shop-floor MES and ERP clients, JDeveloper/Swing and
WinForms tools, Delphi and VB6 holdovers, installer wizards, Device Manager, IIS Manager.
If a person can click it, this can click it — no automation interface required.

**Looking at problems you can't diagnose.** An error dialog you don't recognize, a service
that won't start, a machine that got slow. Claude reads the dialog (often via `Ctrl+C`,
which copies the full text on most Windows error boxes), opens Event Viewer, checks Task
Manager, and reports what it actually saw — separating what it read from what it inferred.

`references/local-apps.md` covers both in depth.

---

## What it does

```bash
RC="$HOME/.claude/skills/computer-use/scripts/rc.py"

python "$RC" windows                              # every visible window + coordinates
python "$RC" windowrect "PowerShell"              # (x, y, w, h)
python "$RC" shot out.png --window "PowerShell"   # capture just that window
python "$RC" shot out.png X Y W H --scale 3       # zoom in on small text

python "$RC" click X Y --focus "Notepad"          # click, guarded
python "$RC" key ctrl v --focus "Notepad"
python "$RC" drag X1 Y1 X2 Y2
python "$RC" type "한글도 이모지도 IME 없이"

python "$RC" clipfile script.txt                  # push text via clipboard
python "$RC" getclip result.txt                   # pull results back
```

Every coordinate is **screenshot pixels** — read them straight off the image you just looked at.
DPI conversion happens inside.

---

## The focus guard

The single most important thing here.

```bash
python "$RC" key enter --focus "PowerShell"
```

`--focus` brings the target window to the front and **refuses to send input if it can't**.

Without it, a keystroke meant for a console lands in whatever has focus. During development
a 2.5 KB PowerShell command got pasted into a browser search box and submitted, because focus
had silently moved. The guard exists because of that.

```
$ python rc.py key enter --focus "no-such-window"
RuntimeError: window not found      # nothing was typed
```

---

## RDP, when a server only gives you port 3389

Same technique, one more target. If a server has 3389 open and nothing else — no WinRM,
no SSH, no SMB — you can still work on it. A human connects with Remote Desktop;
Claude drives the session.

Commands go in through the clipboard. Results come back the same way:

```powershell
Start-Transcript -Path 'C:/temp/out.txt' -Force | Out-Null
Get-Service | Where-Object Status -eq 'Stopped'
Stop-Transcript | Out-Null
Set-Clipboard -Value (Get-Content 'C:/temp/out.txt' -Raw)
```

```bash
python "$RC" getclip result.txt
```

No file share, no agent to install.

**One caveat worth knowing before you start:** from outside, the whole RDP session is a single
window. Nothing can tell you which app is in front *inside* it. So you capture and look before
every click in there. `references/rdp.md` covers the full playbook.

---

## Hard-won notes

`references/pitfalls.md` documents ten failures and their fixes, all hit for real:

- keystrokes leaking into the wrong app when focus moves
- mixed-DPI setups where three coordinate systems disagree (6400×1600 vs 9600×1620 vs 6400×1080)
- one emoji in a window title killing a script on a cp949 console
- Defender's AMSI blocking gzip+base64 bootstraps as obfuscated malware — correctly
- backslashes collapsing on the way to Python, turning `C:\temp` into `C:<TAB>emp`
- WebGL `toDataURL` returning a blank frame outside `requestAnimationFrame`

---

## Scope

Windows only. Linux/macOS would need a different capture and input layer; the design
(screenshot coordinates, focus guard, clipboard transport) should carry over.

Actions that are hard to undo — deleting files, changing settings, sending mail — should be
confirmed with you first, and the skill says so. Treat it as a capable pair of hands that
still needs a second opinion before anything irreversible.

## License

MIT
