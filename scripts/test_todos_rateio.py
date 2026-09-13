import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.sessions.backends.db import SessionStore
from django.template.loader import render_to_string
from regrarateio.models import LancamentoRateio
from regrarateio.views import LancamentoRateioList

print('sem cap/car:', LancamentoRateio.objects.filter(
    conta_pagar__isnull=True, conta_receber__isnull=True
).count())

rf = RequestFactory()
req = rf.get(
    '/regrarateio/lancamentos/',
    {'data_inicio': '2026-06-01', 'data_fim': '2026-06-30', 'socio': '39', 'tipo': ''},
)
session = SessionStore()
session['empresa_id'] = 16
session.save()
req.session = session

view = LancamentoRateioList.as_view()
try:
    resp = view(req)
    resp.render()
    print('status', resp.status_code)
    content = resp.content.decode('utf-8', errors='replace')
    print('REF A ISS in page', 'REF A ISS' in content)
    print('len', len(content))
except Exception:
    import traceback
    traceback.print_exc()

from django.template import Context, Engine
from regrarateio.models import LancamentoRateio

lr = LancamentoRateio.objects.get(pk=8518)
for snippet in [
    '{% if row.conta_pagar_id %}cap{% else %}rec{% endif %}',
    '{% if row.conta_pagar_id %}R$ x{% else %}R$ {{ row.conta_receber.valor_a_receber }}{% endif %}',
    '{% if row.conta_pagar_id and row.conta_pagar.cobranca %}a{% elif row.conta_receber.forma_pagamento %}b{% else %}c{% endif %}',
]:
    t = Engine.get_default().from_string(snippet)
    try:
        print(snippet[:50], '->', t.render(Context({'row': lr})))
    except Exception as e:
        print(snippet[:50], 'ERR', type(e).__name__, e)

from django.urls import reverse
try:
    print('reverse None', reverse('regrarateio:lancamentoRateioEdit', args=['car', None]))
except Exception as e:
    print('reverse None ERR', type(e).__name__, e)

turl = Engine.get_default().from_string(
    "{% load %}<a href=\"{% url 'regrarateio:lancamentoRateioEdit' 'car' tid %}\">"
)
try:
    print('url tag None', turl.render(Context({'tid': None})))
except Exception as e:
    print('url tag None ERR', type(e).__name__, e)
