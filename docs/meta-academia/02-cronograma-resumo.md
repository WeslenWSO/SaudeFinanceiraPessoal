# Cronograma — Resumo de horas e prazos

## Premissas

- **1 desenvolvedor**, ~**6 h/dia** úteis
- Horas incluem: backend Django, templates, testes manuais, deploy Render
- Início sugerido: **01/09/2026**

---

## Comparativo: sem IA vs. com IA (Cursor)

| Fase | Escopo | Sem IA | Com IA | Redução |
|------|--------|-------:|-------:|--------:|
| **0** | Menu + seeds + doc | 9 h | **4 h** | ~55% |
| **1** | Aferição + fechamento mensal | 58 h | **32 h** | ~45% |
| **1b** | Metas em lote *(opcional)* | 8 h | **4 h** | ~50% |
| **2** | LRD, SOPs, painel gerencial | 100 h | **60 h** | ~40% |
| **3** | Padrinho, vendas, coord. técnica | 90 h | **55 h** | ~39% |
| **4** | PDF, multi-unidade, certificação | 80 h | **45 h** | ~44% |
| | **MVP (0+1)** | **67 h** | **~36 h** | ~46% |
| | **Até recepção (0+1+2)** | **167 h** | **~96 h** | ~43% |
| | **Projeto completo (0–4)** | **337 h** | **~200 h** | ~41% |

**Calendário com IA:** MVP ~6 dias úteis | recepção ~3 semanas | completo ~1,5 mês.

---

## Cronograma sem IA (referência tradicional)

| Fase | Escopo | Horas | Dias (~6h) | Semanas | Período |
|------|--------|------:|---------:|--------:|---------|
| 0 | Menu + seeds + doc | 9 | 1,5 | 0,5 | 01–02 set |
| 1 | Aferição automática | 58 | 10 | 2 | 02–15 set |
| 1b | Metas em lote *(opc.)* | 8 | 1,5 | 0,5 | 16–17 set |
| 2 | LRD + SOPs + painel | 100 | 17 | 3,5 | 18 set – 10 out |
| 3 | Padrinho + vendas | 90 | 15 | 3 | 13 out – 31 out |
| 4 | PDF + integrações | 80 | 13 | 2,5 | nov – dez |
| | **Total MVP** | **67** | **11** | **2,5** | |
| | **Total 0+1+2** | **167** | **28** | **6** | |
| | **Total completo** | **337** | **56** | **11** | |

---

## Cronograma com IA — marcos

| Data alvo | Marco | Horas acum. |
|-----------|-------|------------:|
| **08 set 2026** | MVP aferição mensal em produção | ~36 h |
| **26 set 2026** | Operação recepção (LRD + cancelamentos + painel) | ~96 h |
| **24 out 2026** | Padrinho + vendas + coord. técnica | ~151 h |
| **21 nov 2026** | PDF + multi-unidade + certificação | ~200 h |

---

## Custo referencial (taxa R$ 120/h)

| Escopo | Sem IA | Com IA |
|--------|-------:|-------:|
| MVP | ~R$ 8.040 | ~R$ 4.320 |
| Completo | ~R$ 40.440 | ~R$ 24.000 |

**Buffer recomendado:** +10% com IA (~20 h) | +15% sem IA (~50 h)

---

## Custo de tokens + 30% Cursor AI

### Premissas de orçamento

- Referência de modelo: **GPT-5.6 Terra no Cursor**
- Preço de referência: **US$ 2/1M tokens de entrada** e **US$ 12/1M tokens de saída**
- Perfil estimado: **5 tokens de entrada para 1 token de saída**
- Custo médio ponderado: **~US$ 3,67 por 1M tokens totais**
- Câmbio de planejamento: **US$ 1 = R$ 5,50**
- Reserva Cursor AI: **30% sobre o custo estimado de tokens**
- Valores são orçamento de consumo. A franquia incluída no plano Cursor pode reduzir a cobrança efetiva.

### Orçamento consolidado com IA

| Escopo | Horas com IA | Mão de obra | Tokens estimados | Custo-base tokens | Tokens + 30% Cursor | Total mão de obra + IA |
|--------|-------------:|-------------:|------------------:|------------------:|--------------------:|-----------------------:|
| MVP (0+1) | 36 h | R$ 4.320,00 | ~16,4 M | R$ 330,00 | **R$ 429,00** | **R$ 4.749,00** |
| Até recepção (0+1+2) | 96 h | R$ 11.520,00 | ~40,9 M | R$ 825,00 | **R$ 1.072,50** | **R$ 12.592,50** |
| Projeto completo (0–4) | 200 h | R$ 24.000,00 | ~81,8 M | R$ 1.650,00 | **R$ 2.145,00** | **R$ 26.145,00** |

### Fórmula para atualização

`Custo IA em R$ = custo de tokens em US$ × câmbio × 1,30`

`Custo total = horas com IA × R$ 120 + custo IA em R$`

> Para faturamento, substituir a estimativa pelo consumo exibido no painel do Cursor. O adicional de 30% funciona como reserva para variação de contexto, reprocessamentos e uso de modelos mais caros.
