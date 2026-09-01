# Marcos de entrega (go-live)

## Critérios de pronto por fase

| Fase | Entregável | Critério de pronto |
|------|------------|-------------------|
| **0** | Menu + premiação | 4 itens em Meta Academia; seeds Atendente completos |
| **1** | Aferição mensal | Fechar mês calcula Conversão/Vendas/Churn; extrato premiação |
| **2** | Operação recepção | KPIs gerente visíveis; LRD registrável; cancelamentos categorizados |
| **3** | Padrinho + vendas | % régua e retenção D90 no painel |
| **4** | Integrações | PDF extrato; multi-unidade; certificação por setor |

---

## Linha do tempo — com IA (recomendado)

| Data | Marco | Horas acum. | O que a operação ganha |
|------|-------|------------:|------------------------|
| **08 set 2026** | MVP Fase 0+1 | ~36 h | Cadastro meta mensal + aferição automática + fechamento |
| **26 set 2026** | Fase 2 | ~96 h | LRD, SOPs, painel KPIs, reunião retenção |
| **24 out 2026** | Fase 3 | ~151 h | Padrinho, vendas, coordenação técnica |
| **21 nov 2026** | Fase 4 | ~200 h | PDF, multi-unidade, certificação |

---

## Linha do tempo — sem IA (referência)

| Data | Marco | Horas acum. |
|------|-------|------------:|
| **15 set 2026** | MVP Fase 0+1 | 67 h |
| **10 out 2026** | Fase 2 | 167 h |
| **31 out 2026** | Fase 3 | 257 h |
| **15 dez 2026** | Fase 4 | 337 h |

---

## Diagrama Gantt (marcos)

```mermaid
gantt
  title Meta Academia — Cronograma
  dateFormat YYYY-MM-DD
  axisFormat %d/%m

  section Fase0
  Menu_e_seeds           :f0, 2026-09-01, 2d

  section Fase1
  Modelo_afericao        :f1a, 2026-09-02, 3d
  Dashboard_fechamento   :f1b, after f1a, 3d

  section Fase2
  Modelos_operacionais   :f2a, 2026-09-09, 5d
  Painel_LRD_SOPs        :f2b, after f2a, 5d

  section Fase3
  Padrinho_vendas        :f3, 2026-09-26, 10d

  section Fase4
  PDF_multi_integracao   :f4, 2026-10-24, 8d
```

*Gantt acima calibrado para ritmo **com IA** (~6 h/dia).*

---

## Fluxo operacional mensal (pós Fase 1)

1. Gerente cadastra **metas do mês**
2. Recepção faz **lançamentos diários** durante o mês
3. Gerente informa **qt. ativos** e **cancelados**
4. Gerente clica **Recalcular aferição** → sistema preenche Conversão, Vendas, Churn
5. Gerente informa **NPS** e demais indicadores manuais
6. Gerente **fecha o mês** → extrato de premiação por área
