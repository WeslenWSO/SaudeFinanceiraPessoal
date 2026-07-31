#!/usr/bin/env python
import os, sqlite3, sys
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
conn = sqlite3.connect(ROOT / "db.sqlite3")
sq = Counter()
for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE 'notasfiscais_%' OR name LIKE 'notafiscalentrada_%')"):
    sq[t] = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
conn.close()
os.environ["DATABASE_URL"] = (ROOT / "render_db.url").read_text().strip()
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")
import django; django.setup()
from django.apps import apps
pg = Counter()
for m in apps.get_models():
    if m._meta.app_label in ("notasfiscais", "notafiscalentrada"):
        pg[m._meta.db_table] = m.objects.count()
print("SQLITE vs POSTGRES — notas fiscais:")
for t in sorted(set(sq) | set(pg)):
    s, p = sq.get(t, 0), pg.get(t, 0)
    mark = "OK" if s == p else f"DIFF {p-s:+d}"
    print(f"  {t}: sqlite={s} postgres={p} [{mark}]")
