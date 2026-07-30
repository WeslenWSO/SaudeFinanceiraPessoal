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

Serviço **separado** do projeto pessoal (`financaspessoais-eloo`).

1. Faça push da branch `main` para o GitHub.
2. No [Render Dashboard](https://dashboard.render.com): **New → Blueprint**.
3. Conecte o repositório `WeslenWSO/SaudeFinanceiraPessoal`.
4. O [`render.yaml`](render.yaml) cria automaticamente:
   - PostgreSQL `saudefinanceira-pessoal-db`
   - Web Service `saudefinanceira-pessoal` com `DATABASE_URL` vinculado
5. Após o deploy, abra **Shell** do Web Service e rode:
   ```bash
   python manage.py createsuperuser
   ```
6. Acesse `https://saudefinanceira-pessoal.onrender.com/login/` (ajuste a URL se o Render gerar nome diferente — atualize `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS` no painel).

Build usa [`requirements-render.txt`](requirements-render.txt) (sem pacotes exclusivos do Windows).
