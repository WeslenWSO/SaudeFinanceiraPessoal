# Correções no servidor (erro 500 / Gunicorn)

## 1. Erro: `ImportError: cannot import name 'lazy_annotations' from 'django.utils.inspect'`

**Causa:** Algum pacote ou o admin do Django tenta importar `lazy_annotations`, que só existe no Django 5.2+. No projeto usamos Django 4.2.

**O que foi feito no código:** Foi adicionado um *stub* de compatibilidade em `SaudeFinanceira/wsgi.py` e em `manage.py`: antes de carregar o resto do Django, é definido `lazy_annotations` em `django.utils.inspect` quando ele não existir. Assim o import deixa de falhar.

**No servidor:** Garanta que está usando o código atual (com esse patch), reinicie o Gunicorn e teste de novo.

---

## 2. Erro: `[ERROR] Control server error: [Errno 98] Address '.../gunicorn.ctl' is already in use`

**Causa:** O socket de controle do Gunicorn (`gunicorn.ctl`) ficou em uso porque uma instância anterior não encerrou corretamente.

**Passos no servidor (Linux):**

```bash
cd /var/www/html/SaudeFinanceira

# Parar processos Gunicorn antigos
pkill -f gunicorn
# ou, se usar systemd:
# sudo systemctl stop gunicorn

# Remover o socket antigo (se existir)
rm -f gunicorn.ctl

# Subir de novo (exemplo com gunicorn na venv)
source venv/bin/activate
gunicorn --bind 0.0.0.0:8000 SaudeFinanceira.wsgi:application
# ou reiniciar o serviço systemd
```

---

## 3. Garantir versão do Django no servidor

Para evitar mistura de versões (que pode gerar o `lazy_annotations` ou `KeyError: 'django'`):

```bash
cd /var/www/html/SaudeFinanceira
source venv/bin/activate
pip install "Django==4.2.2" --force-reinstall
# Depois reinicie o Gunicorn
```

Depois dessas correções, faça um novo deploy, reinicie o Gunicorn e teste o login novamente.
