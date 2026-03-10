# semiCLICK

`semiCLICK` is a small Windows-only Python overlay for running simple keyboard macros over Minecraft with a safety-first workflow.

## Features

- Always-on-top overlay window with click-through gameplay mode
- Step-based macro editor for key taps and waits
- Global hotkeys for start, stop, panic stop, and overlay interaction toggle
- Safety gate that only sends keys while Minecraft is focused
- Auto-pause when focus leaves Minecraft and resume when it returns
- JSON persistence for one saved sequence and app settings

## Install

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Run

```powershell
$env:PYTHONPATH = "src"
python -m semiclick
```

## Defaults

- Start hotkey: `ctrl+shift+f5`
- Stop hotkey: `ctrl+shift+f6`
- Panic hotkey: `ctrl+shift+f7`
- Toggle overlay interaction: `ctrl+shift+f8`

## Notes

- Global hotkeys may require elevated privileges on some Windows setups.
- Minecraft focus detection matches either a window title containing `Minecraft` or the process names `javaw.exe` and `Minecraft.Windows.exe`.
