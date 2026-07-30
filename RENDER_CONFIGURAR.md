# Configurar FinancasPessoais no Render

Servico: https://dashboard.render.com/web/srv-d9hui8jtqb8s73a97d70  
URL: https://financaspessoais-eloo.onrender.com  
Banco: https://dashboard.render.com/d/dpg-d9hurgo4n6ts73bj8pkg-a (financas-db)

## 1. Build & Deploy

Settings -> Build & Deploy:

| Campo | Valor |
|-------|--------|
| Repository | `WeslenWSO/SaudeFinanceiraPessoal` |
| Branch | `main` |
| Build Command | `bash build.sh` |
| Start Command | `bash start.sh` |

Save.

## 2. Banco PostgreSQL (DATABASE_URL)

**Opcao A — mais facil (recomendado)**

1. Abra **FinancasPessoais** -> **Environment**
2. Clique **Add Environment Variable** -> **Add from Database**
3. Selecione **financas-db**
4. Nome: `DATABASE_URL` | Property: **Internal Database URL**
5. Save

**Opcao B — manual**

1. Abra **financas-db** -> **Connect**
2. Copie **Internal Database URL**
3. Em **FinancasPessoais** -> **Environment** -> adicione `DATABASE_URL`

## 3. Demais variaveis (Environment)

| Variavel | Valor |
|----------|--------|
| `PYTHON_VERSION` | `3.12.4` |
| `DJANGO_DEBUG` | `false` |
| `ALLOWED_HOSTS` | `financaspessoais-eloo.onrender.com,.onrender.com` |
| `CSRF_TRUSTED_ORIGINS` | `https://financaspessoais-eloo.onrender.com` |

Save.

## 4. Deploy

**Manual Deploy** -> Deploy latest commit.

## 5. Admin e dados

Shell:

```bash
python manage.py createsuperuser
```

Importar SQLite local (no PC):

```powershell
.\scripts\importar_para_postgres.ps1 -DatabaseUrl "postgresql://..."
```
