# Plano geral — Meta Academia (Aferição de Metas Mensais)

## Objetivo

Evoluir o app `indicadores` para **cadastro mensal de metas** e **aferição automática de resultados**, alinhado ao Projeto Blue 7K (Bluefit Maceió).

---

## Contexto atual no sistema

| Camada | Status |
|--------|--------|
| Cadastro Indicador / Atendente | Implementado |
| Meta mensal (PeriodoAcademia + ItemPeriodoAcademia) | Implementado (entrada manual) |
| Lançamento diário (vendas, conversão, cancelamentos) | Implementado |
| Premiação (proporcional + faixas CHURN) | Implementado |
| Dashboard mensal | Implementado |
| **Gap:** planilha diária **não alimenta** resultados mensais automaticamente | Pendente (Fase 1) |
| SOPs, LRD, régua padrinho (docs Blue 7K) | Não implementado (Fases 2–3) |

---

## Conceito: aferição de meta mensal

1. **Meta** — cadastrada por indicador, mês e empresa
2. **Resultado aferido** — com origem:
   - `MANUAL` — NPS, montagem de treino
   - `CALCULADO` — Conversão, Vendas, Churn (Fase 1)
   - `OPERACIONAL` — LRD, SOP, padrinho (Fases 2+)
3. **Status do período** — RASCUNHO → FECHADO
4. **Premiação** — recalculada ao fechar o mês

---

## Mapeamento documentação Blue 7K

### Treinamento por setor (doc 03)

| Setor | KPIs | Sistema |
|-------|------|---------|
| Recepção | LRD, auditoria SOP | Fase 2 |
| Padrinho | Régua 90d, retenção D90 | Fase 3 |
| Gerente | Painel churn, adds, NPS | Fase 1 parcial → Fase 2 |
| Coord. técnica | D90, avaliações, ocupação | Fase 3 |
| Vendas | Matrículas, comissão D60 | Fase 3 |

### 7 SOPs recepção (doc 04)

SOP 1–7 mapeados para registros operacionais na Fase 2 (cancelamentos, cobrança, reclamações, prospects).

---

## Indicadores padrão (seed)

**Musculação:** NPS GERAL, NPS MUSCULAÇÃO, NPS POR HORA, MONTAGEM DE TREINO, CHURN

**Atendente:** NPS geral, NPS recepção, NPS por horario, Conversão, Vendas, Redução inadimplentes

---

## Recomendação

Priorizar **Fase 0 + Fase 1** (~36 h com IA): conecta lançamento diário ao dashboard, formaliza fechamento mensal e extrato de premiação — núcleo da aferição de meta sem depender dos SOPs completos.

Ver cronograma: [02-cronograma-resumo.md](02-cronograma-resumo.md)
