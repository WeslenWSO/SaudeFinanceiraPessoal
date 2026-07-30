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

URL: **https://financaspessoais-eloo.onrender.com** (plano **Standard** — sempre ativo)

Guia passo a passo: [`RENDER_CONFIGURAR.md`](RENDER_CONFIGURAR.md)

Mapa de recursos no Render: [`RENDER_DOIS_PROJETOS.md`](RENDER_DOIS_PROJETOS.md)

Resumo:

1. [FinancasPessoais](https://dashboard.render.com/web/srv-d9hui8jtqb8s73a97d70) -> **Build & Deploy**: `bash build.sh` / `bash start.sh`
2. **Environment** -> **Add from Database** -> `financas-db` -> `DATABASE_URL` (Internal)
3. Variaveis: `PYTHON_VERSION=3.12.4`, `DJANGO_DEBUG=false`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` (ver [`render.env.example`](render.env.example))
4. **Manual Deploy**
5. Shell: `python manage.py createsuperuser`
6. Importar dados: `scripts/importar_para_postgres.ps1`

**Imagens do login:** logo e fundos ficam em `static/media/` (versionados no Git). O `.gitignore` ignora só `/media/` (uploads), nao `static/media/`.

Desenvolvimento local: `pip install -r requirements-local.txt`
