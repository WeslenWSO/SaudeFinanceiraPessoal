# Render — Saude Financeira (unico app)

O servico **`financas-pessoais-0muq`** (repo `FinancasPessoais`) foi **removido** do Render.

Use apenas:

| Recurso | URL / nome |
|---------|------------|
| **Web** | https://financaspessoais-eloo.onrender.com |
| **Servico** | `FinancasPessoais` (`srv-d9hui8jtqb8s73a97d70`) |
| **Postgres** | `financas-db` |
| **Repositorio** | `WeslenWSO/SaudeFinanceiraPessoal` |

## Environment (web eloo)

| Variavel | Valor |
|----------|--------|
| `DATABASE_URL` | Internal URL do **`financas-db`** |
| `PYTHON_VERSION` | `3.12.4` |
| `DJANGO_DEBUG` | `false` |
| `ALLOWED_HOSTS` | `financaspessoais-eloo.onrender.com,.onrender.com` |
| `CSRF_TRUSTED_ORIGINS` | `https://financaspessoais-eloo.onrender.com` |

## Login

https://financaspessoais-eloo.onrender.com/login/

- Usuario: `saude`
- Senha: `Sqt!98315`

Redefinir senha no Postgres (PC, com `render_db.url`):

```powershell
.\scripts\garantir_usuario_postgres.ps1 -Username saude -Password "Sqt!98315" -Superuser -VincularEmpresas
```

Guia completo: [`RENDER_CONFIGURAR.md`](RENDER_CONFIGURAR.md)
