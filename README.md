# SaudeFinanceiraPessoal

Sistema de gestão financeira pessoal baseado no projeto SaudeFinanceira (Django).

## Requisitos

- Python 3.11+
- Git

## Instalação

```powershell
cd SaudeFinanceiraPessoal
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Acesse: http://127.0.0.1:8000/login/

## Variáveis de ambiente (opcional)

```powershell
$env:DJANGO_DEBUG = "true"
$env:GEMINI_API_KEY = "sua-chave"
$env:OPENAI_API_KEY = "sua-chave"
```

## Banco de dados

Por padrão usa SQLite (`db.sqlite3`). Para produção, configure `DATABASES` em `SaudeFinanceira/settings.py`.

Após `migrate`, cadastre ao menos uma empresa no admin antes que algumas migrações de dados rodem (ex.: `regrarateio`).

## Repositório

- **Remoto:** https://github.com/WeslenWSO/SaudeFinanceiraPessoal.git
- **Branch principal:** main

## Deploy no Render (SaudeFinanceiraPessoal)

URL: **https://financaspessoais-eloo.onrender.com**

Guia detalhado: [`RENDER_CONFIGURAR.md`](RENDER_CONFIGURAR.md) · mapa de recursos: [`RENDER_DOIS_PROJETOS.md`](RENDER_DOIS_PROJETOS.md)

### Blueprint (`render.yaml`)

1. **Dashboard Render → New → Blueprint** e selecione este repositório (ou conecte o repo existente).
2. O blueprint cria o **PostgreSQL** (`financas-db`) e o **Web Service** com `DATABASE_URL` automático.
3. Após o primeiro deploy, abra o **Shell** do serviço:

```bash
python manage.py createsuperuser
```

4. Cadastre ao menos uma **empresa** no admin (algumas migrações dependem disso).
5. Variáveis opcionais no painel (ver [`render.env.example`](render.env.example)):
   - `GEMINI_API_KEY` — OCR/Gemini em importações
   - `NFSE_NACIONAL_*` — certificados NFS-e nacional

### Build e start

| Etapa | Comando |
|-------|---------|
| Build | `bash build.sh` — instala Tesseract OCR, `pip install -r requirements-render.txt`, `collectstatic`, `migrate` |
| Start | `bash start.sh` — `migrate`, `collectstatic`, diagnóstico de banco, `gunicorn` |

Dependências de produção: **`requirements-render.txt`** (Linux). Desenvolvimento Windows: **`requirements-local.txt`**.

### Migração SQLite → Postgres (opcional)

```powershell
# Local: exportar backup
python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.Permission > backup_render.json

# Render Shell (após migrate): importar em lotes
python scripts/importar_para_postgres_lotes.py
# ou só o que falta:
python scripts/importar_faltantes.py
```

Faça backup antes. Script PowerShell: `scripts/importar_para_postgres.ps1`.

### Limitações (Render)

| Recurso | Comportamento |
|---------|----------------|
| PostgreSQL | Persiste |
| Arquivos em `media/` (uploads) | **Não persistem** após redeploy — use Render Disk ou S3 |
| `static/media/` (logo, fundos login) | Versionados no Git — persistem via `collectstatic` |
| Plano free | Instância dorme (~50s cold start) |
| OCR/PDF pesado | Pode exigir mais memória |

**Imagens do login:** ficam em `static/media/` (Git). O `.gitignore` ignora só `/media/` (uploads de usuário).

### Checklist pós-deploy

- [ ] Logs do build: `collectstatic` e `migrate` sem erro
- [ ] `/login/` abre com CSS (WhiteNoise + `DEBUG=false`)
- [ ] Login com usuário criado no Shell
- [ ] `DATABASE_URL` aponta para Postgres (Internal), não SQLite
