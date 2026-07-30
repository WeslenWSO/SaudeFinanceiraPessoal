#!/usr/bin/env python
"""Ajusta requirements.txt para Render (Pillow novo, deps Windows-only)."""
from pathlib import Path

WIN_ONLY = {
    "mysqlclient", "mysql-connector-python", "PyMySQL",
    "PyAutoGUI", "PyGetWindow", "PyScreeze", "MouseInfo", "PyMsgBox", "PyRect",
    "pefile", "tk", "pyinstaller", "pyinstaller-hooks-contrib", "pywin32-ctypes",
    "pywhatkit", "pydev", "pyperclip", "pytweening",
    "distlib", "filelock", "virtualenv",
}
path = Path("requirements.txt")
lines = []
for raw in path.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
        lines.append(raw.rstrip())
        continue
    pkg = line.split("==")[0].split(">=")[0].split(";")[0].strip()
    if pkg == "Pillow":
        lines.append("Pillow>=10.4.0,<12")
        continue
    if pkg in WIN_ONLY and "sys_platform" not in line:
        lines.append(f"{line}; sys_platform == 'win32'")
        continue
    lines.append(line)
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("requirements.txt atualizado")
