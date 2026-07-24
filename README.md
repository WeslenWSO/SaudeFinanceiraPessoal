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
```

## Banco de dados

Por padrão usa SQLite (`db.sqlite3`). Para produção, configure `DATABASES` em `SaudeFinanceira/settings.py`.

## Repositório

- **Remoto:** git@github.com:WeslenWSO/SaudeFinanceiraPessoal.git
- **Branch principal:** main
