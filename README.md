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

URL principal: **https://financaspessoais-eloo.onrender.com**

Serviço **FinancasPessoais** (`srv-d9hui8jtqb8s73a97d70`) apontado para este repositório.

1. Faça push da branch `main` para o GitHub.
2. No [Render Dashboard](https://dashboard.render.com/web/srv-d9hui8jtqb8s73a97d70) → **FinancasPessoais**:
   - **Build & Deploy**: repo `WeslenWSO/SaudeFinanceiraPessoal`, branch `main`, build `bash build.sh`, start `gunicorn SaudeFinanceira.wsgi:application --bind 0.0.0.0:$PORT`
   - **Environment**:
     - `DATABASE_URL` = Internal URL do **financas-db**
     - `DJANGO_DEBUG` = `false`
     - `ALLOWED_HOSTS` = `financaspessoais-eloo.onrender.com,.onrender.com`
     - `CSRF_TRUSTED_ORIGINS` = `https://financaspessoais-eloo.onrender.com`
3. **Manual Deploy** → Deploy latest commit.
4. Após o deploy, abra **Shell** e rode:
   ```bash
   python manage.py createsuperuser
   ```
5. Acesse `https://financaspessoais-eloo.onrender.com/login/`

O [`render.yaml`](render.yaml) documenta a mesma configuração (Blueprint / referência).

Build usa [`requirements-render.txt`](requirements-render.txt) (sem pacotes exclusivos do Windows).
