# Dois projetos no Render

Organizacao recomendada para usar **Financas Pessoais** e **Saude Financeira** ao mesmo tempo.

## Mapa

| Projeto Render | App | URL | Repositório | Banco |
|----------------|-----|-----|-------------|-------|
| **My project** | Financas Pessoais (cadastro simples) | `financas-pessoais-0muq.onrender.com` | Outro repo | Postgres proprio (nao `financas-db`) |
| **SaudeFinanceira** | Saude Financeira (NF, empresas, faturamento) | `financaspessoais-eloo.onrender.com` | `WeslenWSO/SaudeFinanceiraPessoal` | **`financas-db`** |

Sao **dois sites diferentes**. Senha alterada no 0muq **nao** afeta o eloo.

## 1. Mover servicos nos projetos (dashboard)

1. Abra **My project** e anote os web services (nome + URL).
2. Servico com URL **`financas-pessoais-0muq`** → **Settings** → **Project** → **My project**.
3. Servico com URL **`financaspessoais-eloo`** → **Settings** → **Project** → **SaudeFinanceira**.
4. **`financas-db`** (Postgres) → mova para **SaudeFinanceira** (banco do app eloo).

## 2. Saude Financeira (eloo) — Environment

No web service **`financaspessoais-eloo`**:

| Variavel | Valor |
|----------|--------|
| `DATABASE_URL` | **Add from Database** → `financas-db` → **Internal Database URL** |
| `PYTHON_VERSION` | `3.12.4` |
| `DJANGO_DEBUG` | `false` |
| `ALLOWED_HOSTS` | `financaspessoais-eloo.onrender.com,.onrender.com` |
| `CSRF_TRUSTED_ORIGINS` | `https://financaspessoais-eloo.onrender.com` |

**Manual Deploy** → aguarde **Live**.

Nos **Logs** do start, procure:

```
[startup] ENGINE=postgresql HOST=dpg-...
[startup] auth_user count: 5
```

Se aparecer `sqlite3`, o login sempre falha — corrija `DATABASE_URL`.

## 3. Login Saude Financeira

URL: https://financaspessoais-eloo.onrender.com/login/

Credenciais (Postgres `financas-db`):

- Usuario: `saude`
- Senha: `Sqt!98315`

### Redefinir senha do PC (sem Shell do Render)

Com `render_db.url` (External URL do `financas-db`):

```powershell
cd "C:\Users\wesle\OneDrive\Documentos\GitHub\SaudeFinanceiraPessoal"
.\scripts\garantir_usuario_postgres.ps1 -Username saude -Password "Sqt!98315" -Superuser -VincularEmpresas
```

### Shell no Render (alternativa)

```bash
python manage.py diagnostico_banco --skip-checks
python manage.py garantir_usuario saude --password "Sqt!98315" --superuser --vincular-empresas --skip-checks
python manage.py diagnostico_banco --testar-login saude --senha "Sqt!98315" --skip-checks
```

## 4. Financas Pessoais (0muq)

App separado (tela com "Criar conta"). Configure **no repo desse app**:

- Web service proprio em **My project**
- `DATABASE_URL` do **banco desse app** (crie um Postgres novo se ainda nao existir)
- Nao use o `financas-db` a menos que seja o mesmo codigo Django

## 5. Checklist rapido

- [ ] `financaspessoais-eloo` no projeto **SaudeFinanceira**
- [ ] `financas-pessoais-0muq` no projeto **My project**
- [ ] `financas-db` ligado ao web **eloo** via `DATABASE_URL` Internal
- [ ] Deploy **Live** do eloo
- [ ] Login `saude` / `Sqt!98315` em `/login/`

Guia detalhado do eloo: [`RENDER_CONFIGURAR.md`](RENDER_CONFIGURAR.md)
