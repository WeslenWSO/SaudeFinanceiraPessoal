# Cronograma — Detalhamento por tarefa

Horas **sem IA** (referência). Com IA, aplicar ~40–45% de redução. O orçamento consolidado considera mão de obra, tokens e reserva de 30% do Cursor AI (ver [02-cronograma-resumo.md](02-cronograma-resumo.md)).

---

## Fase 0 — Organização (9 h → ~4 h com IA)

| # | Tarefa | h sem IA | h com IA |
|---|--------|--------:|---------:|
| 1 | Mover lançamento + atendentes para menu Meta Academia | 2 | 1 |
| 2 | Seeds premiação área Atendente + migration | 3 | 1 |
| 3 | Mini-doc fluxo mensal (gerente/recepção) | 2 | 1 |
| 4 | Teste permissões menu + deploy | 2 | 1 |
| | **Total** | **9** | **4** |

---

## Fase 1 — Aferição automática (58 h → ~32 h com IA)

| # | Tarefa | h sem IA | h com IA |
|---|--------|--------:|---------:|
| 1 | Migration `status`, `fechado_em/por` em PeriodoAcademia | 3 | 2 |
| 2 | Migration `origem_resultado`, `resultado_aferido_em` | 3 | 2 |
| 3 | Serviço `afericao.py` — agregação mensal | 12 | 6 |
| 4 | Mapeamento indicador → fórmula | 8 | 5 |
| 5 | Ajuste `calculos.py` (proporção + extrato) | 6 | 3 |
| 6 | Views: recalcular, fechar mês, bloqueio | 8 | 4 |
| 7 | Template dashboard: badges, alertas, extrato | 12 | 6 |
| 8 | Bonificação por atendente (agregado mensal) | 4 | 2 |
| 9 | Testes + deploy Render | 2 | 2 |
| | **Total** | **58** | **32** |

---

## Fase 1b — Metas em lote opcional (8 h → ~4 h com IA)

| # | Tarefa | h sem IA | h com IA |
|---|--------|--------:|---------:|
| 1 | Copiar metas do mês anterior | 4 | 2 |
| 2 | Tela Metas do ano (grid 12 meses) | 4 | 2 |
| | **Total** | **8** | **4** |

---

## Fase 2 — Operação recepção (100 h → ~60 h com IA)

| # | Tarefa | h sem IA | h com IA |
|---|--------|--------:|---------:|
| 1 | Model RegistroCancelamento (SOP 3) | 10 | 6 |
| 2 | LRD diária + ContatoLRD | 18 | 11 |
| 3 | AuditoriaSOP (notas 0–3) | 14 | 8 |
| 4 | RegistroReclamacao (VOLTA 24H) | 10 | 6 |
| 5 | Painel KPIs gerencial | 22 | 13 |
| 6 | Relatório reunião mensal retenção | 10 | 6 |
| 7 | Aferição Redução inadimplentes | 8 | 5 |
| 8 | Testes + deploy | 8 | 5 |
| | **Total** | **100** | **60** |

---

## Fase 3 — Padrinho + vendas (90 h → ~55 h com IA)

| # | Tarefa | h sem IA | h com IA |
|---|--------|--------:|---------:|
| 1 | Régua 90 dias + % cumprimento padrinho | 24 | 14 |
| 2 | Retenção D90 | 16 | 10 |
| 3 | Avaliações agendada vs executada | 12 | 7 |
| 4 | Ocupação aulas coletivas | 10 | 6 |
| 5 | Comissão vendas (D60, penalidade 30d) | 16 | 10 |
| 6 | KPIs no fechamento mensal | 8 | 5 |
| 7 | Testes + deploy | 4 | 3 |
| | **Total** | **90** | **55** |

---

## Fase 4 — Escala e integrações (80 h → ~45 h com IA)

| # | Tarefa | h sem IA | h com IA |
|---|--------|--------:|---------:|
| 1 | Export PDF extrato bonificação | 12 | 7 |
| 2 | Multi-unidade (campo unidade ou empresas filhas) | 20 | 11 |
| 3 | Certificação por setor (checklists doc 03) | 24 | 14 |
| 4 | NPS manual estruturado | 8 | 5 |
| 5 | Stub integração CRM/check-in | 16 | 8 |
| | **Total** | **80** | **45** |
