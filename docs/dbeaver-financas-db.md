# DBeaver — conectar no financas-db (Render)

## 1. Reativar o banco (se suspenso)

1. [Render Dashboard](https://dashboard.render.com) → **financas-db**
2. Se aparecer **Suspended** ou **Free database expired** → **Upgrade database**
3. Aguarde status **Available**

## 2. Instalar DBeaver

- Download: https://dbeaver.io/download/
- Ou no PowerShell: `winget install DBeaver.DBeaver`

## 3. Credenciais (Render → financas-db → Connect)

| Campo | Valor |
|-------|--------|
| Host | `dpg-d9hurgo4n6ts73bj8pkg-a.oregon-postgres.render.com` |
| Port | `5432` |
| Database | `financas_db_adei` |
| Username | `financas_db_adei_user` |
| Password | Copiar no Render (ícone olho) |

Use **External Database URL** na sua máquina — **não** use Internal URL.

## 4. Nova conexão no DBeaver

1. **Database** → **New Database Connection** → **PostgreSQL**
2. Aba **Main**: preencha Host, Port, Database, Username, Password
3. Aba **SSL**: marque **Use SSL**, mode **require**
4. **Test Connection** → **Finish**

Ou importe: **Database** → **Driver Manager** não — use **File** → importar de `scripts/dbeaver/financas-db.dbeaver-data-sources.json` (depois informe a senha).

## 5. Django local (opcional)

```powershell
cd "c:\Users\wesle\OneDrive\Documentos\GitHub\SaudeFinanceiraPessoal"
.\scripts\conectar_postgres_render.ps1
```

Ou copie `render_db.url.example` → `render_db.url` e cole a External URL.

## Problemas comuns

| Erro | Solução |
|------|---------|
| Connection refused | Upgrade banco no Render |
| SSL required | SSL mode = require |
| Authentication failed | Copie senha de novo no Render |
