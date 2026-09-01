# Fases de implementação — escopo técnico

## Fase 0 — Organização

- Menu **Meta Academia** (`usuario/menu.py`):
  - Dashboard de Academia
  - Indicadores
  - Lançamento diário academia
  - Atendentes academia
- Seeds premiação área **Atendente** (`PREMIACAO_PROPORCAO_PADRAO`)
- Doc fluxo operacional mensal (1 página)

---

## Fase 1 — Core: meta mensal + aferição automática

### Modelos

**PeriodoAcademia:** `status` (RASCUNHO | FECHADO), `fechado_em`, `fechado_por`

**ItemPeriodoAcademia:** `origem_resultado` (MANUAL | CALCULADO), `resultado_aferido_em`, `observacao_afericao`

### Serviço `indicadores/services/afericao.py`

- `calcular_resultados_mes(empresa_id, ano, mes)`
- `aplicar_afericao(periodo)`
- `fechar_periodo(periodo, user)`

### Aferição automática

| Indicador | Fonte do resultado |
|-----------|-------------------|
| CHURN | PeriodoAcademia.churn_pct |
| Conversão | Σ balcão ÷ Σ oport. balcão (LancamentoVendasDiario) |
| Vendas | Σ total_dia ou vendas por atendente |
| Redução inadimplentes | Σ cancel. inadimplentes (planilha) |
| NPS / Montagem treino | Manual |

### UI Dashboard

- Cadastro de metas vs resultados aferidos
- Botões: Recalcular aferição | Fechar mês
- Badges: Manual / Calculado / Pendente
- Extrato premiação por área

### Arquivos principais

- `indicadores/models.py`
- `indicadores/services/afericao.py` *(novo)*
- `indicadores/services/calculos.py`
- `indicadores/views_dashboard.py`
- `templates/indicadores/dashboard_academia.html`

---

## Fase 2 — Painel gerencial + recepção

### Novos modelos

- `RegistroCancelamento` — 7 categorias SOP 3
- `ListaResgateDiaria` + `ContatoLRD`
- `AuditoriaSOP` — notas 0–3
- `RegistroReclamacao` — VOLTA 24H

### Telas

- Painel KPIs (semanal + diário)
- LRD diária
- Relatório reunião mensal retenção

---

## Fase 3 — Padrinho + coord. técnica + vendas

- Régua 90 dias (14 toques), % cumprimento
- Retenção D90
- Avaliações agendada vs executada
- Ocupação aulas coletivas
- Comissão vendas (matrícula, bônus D60, penalidade 30d)

---

## Fase 4 — Escala

- Multi-unidade (Ponta Verde + Farol)
- PDF extrato bonificação
- Certificação por setor (gate ≥80%)
- Integração CRM / check-in / NPS
