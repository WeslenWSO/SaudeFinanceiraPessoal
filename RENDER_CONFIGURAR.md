# Configurar FinancasPessoais no Render

Servico: https://dashboard.render.com/web/srv-d9hui8jtqb8s73a97d70  
URL: https://financaspessoais-eloo.onrender.com  
Banco: https://dashboard.render.com/d/dpg-d9hurgo4n6ts73bj8pkg-a (financas-db) — **PostgreSQL em execução, dados já importados**

**Plano atual:** Standard (web + banco) — serviço sempre ligado, sem cold start do plano Free.

## Checklist rápido (banco OK)

- [x] PostgreSQL `financas-db` rodando
- [x] Dados importados do SQLite local
- [ ] Web **FinancasPessoais** com `DATABASE_URL` (Internal) apontando para `financas-db`
- [ ] Deploy **Live** (Build + Start sem erro)
- [ ] Login em `/login/` com usuário do backup

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

## 5. Banco de dados

**Se o Postgres já foi importado** (seu caso): pule esta seção. Não rode `createsuperuser` — use o login existente.

**Se ainda não importou**, use o `backup_render.json` no PC:

1. **financas-db** -> **Connect** -> copie **External Database URL**
2. No PowerShell:

```powershell
cd "c:\Users\wesle\OneDrive\Documentos\GitHub\SaudeFinanceiraPessoal"
.\scripts\importar_para_postgres.ps1 -DatabaseUrl "COLE_A_EXTERNAL_URL_AQUI"
```

Alternativa por lotes:

```powershell
$env:DATABASE_URL = "COLE_A_EXTERNAL_URL_AQUI"
python scripts/importar_para_postgres_lotes.py
```

Aguarde **5–15 min**. Login com o **mesmo usuário/senha** do SQLite local.

## 6. Testar

https://financaspessoais-eloo.onrender.com/login/

## 7. Login falha ("Usuario ou senha incorretos")

Quase sempre e um destes casos:

1. **Web sem `DATABASE_URL`** — a app usa SQLite vazio no Render (sem usuarios).
2. **Import feito antes de criar o usuario `saude`** — o Postgres nao tem esse login.
3. **Senha diferente** da que voce usa localmente.

### Passo 1 — Shell no Render

No dashboard **FinancasPessoais** -> **Shell**, rode:

```bash
python manage.py diagnostico_banco
```

- Se aparecer `ENGINE: ...sqlite...` -> falta `DATABASE_URL` (secao 2). Corrija, **Save** e **Manual Deploy**.
- Se `Usuarios: 0` ou nao listar `saude` -> crie/atualize no Shell:

```bash
python manage.py garantir_usuario saude --password "SUA_SENHA" --superuser --vincular-empresas
python manage.py diagnostico_banco --testar-login saude --senha "SUA_SENHA"
```

- Se `saude` existe mas `authenticate(): FALHOU` -> rode `garantir_usuario` de novo (redefine a senha).

### Passo 2 — Usuario existe mas senha nao funciona

Isso e comum quando a senha foi alterada **depois** do `backup_render.json`, ou o web service ainda usa SQLite (nao o Postgres).

**Opcao A — copiar senha do SQLite local (recomendado)**

No PC, com a **External Database URL** do `financas-db`:

```powershell
cd "c:\Users\wesle\OneDrive\Documentos\GitHub\SaudeFinanceiraPessoal"
.\scripts\sincronizar_senha_postgres.ps1 -DatabaseUrl "EXTERNAL_URL" -Username saude
```

Isso copia o hash de senha do `db.sqlite3` local para o Postgres (mesma senha que funciona no PC).

**Opcao B — Shell no Render**

```bash
python manage.py diagnostico_banco --skip-checks --usuario saude
python manage.py garantir_usuario saude --password "SUA_SENHA" --superuser --vincular-empresas
```

**Opcao C — Reimportar tudo**

```powershell
.\scripts\exportar_sqlite.ps1
.\scripts\importar_para_postgres.ps1 -DatabaseUrl "EXTERNAL_URL"
```

### Passo 3 — Conferir logs do deploy

Nos **Logs** do web service, procure:

```
[startup] DATABASE ENGINE: django.db.backends.postgresql
[startup] auth_user count: 4
```

Se aparecer `sqlite3`, o site **nao** esta usando o Postgres migrado — corrija `DATABASE_URL` (secao 2).

## 8. Plano Standard (pós-upgrade)

Com **Standard**, o serviço **não dorme** após inatividade (diferente do Free). Isso evita demora de 30–60 s na primeira requisição e reduz falhas intermitentes de login.

### Conferir no dashboard

| Recurso | Plano esperado |
|---------|----------------|
| **FinancasPessoais** (web) | Standard |
| **financas-db** (Postgres) | Standard ou `basic-1gb` (equivalente) |

Se o Postgres no dashboard aparecer como `basic-1gb` (plano flexível novo), está OK — é o substituto do Standard legado.

### Após mudar o plano

1. Confirme **`DATABASE_URL`** ainda ligado ao `financas-db` (secao 2).
2. **Manual Deploy** do web service.
3. Shell:

```bash
python manage.py diagnostico_banco --skip-checks
```

4. Se faltar `saude`, use `garantir_usuario` (secao 7).

### Opcional — disco persistente (uploads)

Arquivos em `media/` somem a cada redeploy no Render. No plano Standard voce pode anexar um **Disk** ao web service e montar em `/opt/render/project/src/media` (Settings -> Disks). So necessario se voce faz upload de PDFs/XMLs que precisam ficar guardados no servidor.
