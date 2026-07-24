# Relatório de Depuração – forma_pagamento na importação NFSe

Este documento serve como **template de relatório** para preencher após rodar a depuração com `NFS_IMPORT_DEBUG=True` e o comando `debug_nfse_forma_pagamento`.

## Como ativar os logs de depuração

```bash
# Linux/macOS
export NFS_IMPORT_DEBUG=1
python manage.py runserver

# Ou no Windows (PowerShell)
$env:NFS_IMPORT_DEBUG="1"
python manage.py runserver
```

Ou em `settings.py` (apenas desenvolvimento):

```python
NFS_IMPORT_DEBUG = True
```

## Como rodar o teste rápido

```bash
python manage.py debug_nfse_forma_pagamento --skip-checks
# Com logs detalhados (PowerShell):
$env:NFS_IMPORT_DEBUG="1"; python manage.py debug_nfse_forma_pagamento --skip-checks
```

**Importante:** Se `Cobranca.objects.count() = 0`, a forma de pagamento nunca será vinculada. Rode a migration de seed:

```bash
python manage.py migrate cobranca
```

Isso cria PIX, DINHEIRO, CARTAO CREDITO e CARTAO DEBITO em `cobranca.Cobranca` (migration `0003_seed_formas_pagamento_basicas`).

---

## Perguntas do relatório (preencher após análise)

### 1) A discriminação vem preenchida no objeto NotaFiscalServico antes do save()?

- [ ] Sim – exemplo (primeiros 200 chars): _________________
- [ ] Não – discriminacao vazia/nula em: _________________

*Fonte: logs `[NFS_IMPORT_DEBUG] SPED/ABRASF discriminacao extraída` e `nfse_data.discriminacao` em utils.py; e `discriminacao vazia/nula` em models.save().*

---

### 2) O que retorna extract_payment_method_from_description()?

- Retorno observado: _________________ (ex.: PIX, CARTAO CREDITO, None)
- Nota/série do teste: _________________

*Fonte: log `[NFS_IMPORT_DEBUG] extract_payment_method_from_description() retornou=` em models.save().*

---

### 3) _get_cobranca_by_forma_normalizada encontra alguma Cobranca (ou por que não)?

- [ ] Encontrou – id=___, descricao=___
- [ ] Não encontrou – forma_normalizada=___, Cobrancas no banco (id, descricao, tpag): ___

*Fonte: log `[NFS_IMPORT_DEBUG] _get_cobranca_by_forma_normalizada(...) retornou` em models.save(); e `debug_nfse_forma_pagamento` (Cobranca.objects.values_list).*

---

### 4) Existe conflito de import do model Cobranca? Onde?

- [ ] Não – apenas `from cobranca.models import Cobranca` onde necessário
- [ ] Sim – local: _________________ (ex.: `from .models import Cobranca` em views)

*Fonte: grep por `from .models import ... Cobranca` e `from cobranca.models import Cobranca` no projeto.*

---

### 5) O save() ou update_fields ou rollback está impedindo a persistência de forma_pagamento?

- [ ] Não – forma_pagamento_id é preenchido após save (ver logs “Após save()”)
- [ ] Sim – motivo: _________________ (ex.: exceção em gerar_contas_a_receber, update_fields sem forma_pagamento)

*Fonte: logs `[NFS_IMPORT_DEBUG] Antes save()` / `Após save()` em utils.py; e exceção em `gerar_contas_a_receber()` em models.save().*

---

## Patch / correções aplicadas

(Descrever aqui as alterações feitas com base na depuração. Exemplos:)

- **Cobranca vazia:** Se `Cobranca.objects.count() == 0`, rodar `python manage.py migrate cobranca` (seed em `0003_seed_formas_pagamento_basicas`).
- **Import:** Em `notasfiscais.views` usar apenas `from cobranca.models import Cobranca` (não importar Cobranca de `.models`).
- **update_fields:** Se algum código chamar `nfse.save(update_fields=[...])` sem incluir `forma_pagamento`, incluir o campo ou não passar `update_fields`.
- **gerar_contas_a_receber:** Exceções são logadas com `logger.exception` no save(); corrigir a causa (ex.: ContaAReceber com campos obrigatórios).

---

## Respostas típicas (após rodar depuração)

| # | Pergunta | Resposta típica |
|---|----------|-----------------|
| 1 | discriminacao vem preenchida? | **Sim**, quando o XML contém tag de discriminação (ex.: `serv/cServ/xDescServ` no SPED, `discriminacao` no ABRASF). Logs mostram `len` e primeiros 200 caracteres. |
| 2 | extract_payment_method_from_description retorna? | **Sim**, para textos como "Forma de pagamento: PIX", "Forma de pagamento: CC AUT:..."; retorna PIX, CARTAO CREDITO, CARTAO DEBITO, DINHEIRO, etc. |
| 3 | _get_cobranca_by_forma_normalizada encontra Cobranca? | **Só se existir registro em Cobranca** com `descricao` ou `tpag` compatível. Se `Cobranca.objects.count() == 0`, retorna sempre **None**. Solução: rodar migration de seed (cobranca). |
| 4 | Conflito de import Cobranca? | **Não** em `notasfiscais`: views e demais usam `from cobranca.models import Cobranca`. (A pasta `notasfiscais - Copia` tinha `from .models import Cobranca`; não é usada em produção.) |
| 5 | save/update_fields/rollback impedindo? | **Não**: o fluxo de importação chama `nfse.save()` sem `update_fields`. Se `gerar_contas_a_receber()` lançar exceção, ela é logada e re-lançada (não há rollback silencioso). |
