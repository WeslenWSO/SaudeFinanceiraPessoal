# MCP — Saúde Financeira

Servidor [Model Context Protocol](https://modelcontextprotocol.io/) para consultar o app (empresas, faturamento, fluxo de caixa) com **token de API**.

Dependência: **`mcp>=1.30,<2`** (no `requirements-render.txt`). Não use `pip install mcp` sem pin — a série 2.x renomeou `FastMCP` e quebra este servidor até migrarmos.

## 1. Gerar o API token

No PC (na raiz do projeto):

```powershell
python -m mcp_financas.gerar_token
```

Copie o valor e defina como **`MCP_API_TOKEN`** (nunca commite no Git).

## 2. Cursor (local, stdio)

Arquivo `.cursor/mcp.json` (use o exemplo em `.cursor/mcp.json.example`):

```json
{
  "mcpServers": {
    "saude-financeira": {
      "command": "python",
      "args": ["-m", "mcp_financas", "--transport", "stdio"],
      "cwd": "C:/Users/wesle/OneDrive/Documentos/GitHub/SaudeFinanceiraPessoal",
      "env": {
        "MCP_API_TOKEN": "COLE_SEU_TOKEN",
        "DJANGO_SETTINGS_MODULE": "SaudeFinanceira.settings",
        "DATABASE_URL": "..."
      }
    }
  }
}
```

Reinicie o Cursor. Tools: `mcp_listar_empresas`, `mcp_resumo_faturamento`, `mcp_resumo_fluxo_caixa`, `mcp_health_check`.

## 3. Render (HTTP)

Crie um **segundo Web Service** (ou use o mesmo repo com start command diferente):

| Campo | Valor |
|--------|--------|
| Build | `bash build.sh` |
| Start | `python -m mcp_financas --transport streamable-http` |
| `MCP_API_TOKEN` | token gerado (Secret) |
| `MCP_TRANSPORT` | `streamable-http` |
| `MCP_STATELESS_HTTP` | `true` |
| `DATABASE_URL` | mesmo Postgres do app (`financas-db`) |
| `DJANGO_SETTINGS_MODULE` | `SaudeFinanceira.settings` |
| `SECRET_KEY` | igual ao web principal |

Endpoint MCP (FastMCP): **`https://SEU-SERVICO.onrender.com/mcp`**  
Autenticação: header `Authorization: Bearer SEU_MCP_API_TOKEN`.

No Cursor (cliente remoto), configure o servidor MCP com URL + bearer conforme a documentação atual do Cursor para HTTP/SSE.

## 4. LLM com function calling (`llm.py`)

Mesmas tools via Gemini (requer `GEMINI_API_KEY`):

```powershell
python -c "
from mcp_financas.llm import perguntar_financas
print(perguntar_financas('Quantos faturamentos em setembro 2026?', empresa_id=16))
"
```

## Tools disponíveis

| Tool | Descrição |
|------|-----------|
| `health_check` | Ping + banco |
| `listar_empresas` | IDs e razão social |
| `resumo_faturamento` | Período + totais (sem montar grade) |
| `resumo_fluxo_caixa` | Receita/despesa/resultado por mês |

Todas são **somente leitura**.
