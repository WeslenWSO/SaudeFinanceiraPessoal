#!/usr/bin/env python
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")

if not os.environ.get("DATABASE_URL"):
    url = ROOT / "render_db.url"
    if url.is_file():
        os.environ["DATABASE_URL"] = url.read_text(encoding="utf-8").strip()

import django

django.setup()

from django.db import connection
from servicos_medicos.models import ServicosMedicos

db = connection.settings_dict
print(f"Banco: {db.get('ENGINE')} / {db.get('NAME')}")
print(f"Host: {db.get('HOST')}")
print(f"Total ServicosMedicos: {ServicosMedicos.objects.count()}")
for prefix, label in [("408", "RX"), ("409", "US"), ("410", "TC"), ("411", "RM")]:
    print(f"TUSS {prefix} ({label}): {ServicosMedicos.objects.filter(codigo__startswith=prefix).count()}")

print("\nUltimos 5 cadastros (id desc):")
for s in ServicosMedicos.objects.order_by("-id")[:5]:
    print(f"  id={s.id} | {s.codigo} | {s.servicos[:70]}")
