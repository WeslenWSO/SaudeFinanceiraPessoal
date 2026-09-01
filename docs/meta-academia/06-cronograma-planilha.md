# Cronograma — planilha (importar no Excel)

Copie a tabela abaixo ou use o bloco CSV no final deste arquivo.

| Fase | Tarefa | h sem IA | h com IA | Início | Fim (IA) | Marco |
|------|--------|--------:|---------:|--------|----------|-------|
| 0 | Menu Meta Academia | 2 | 1 | 01/09 | 01/09 | |
| 0 | Seeds premiação Atendente | 3 | 1 | 01/09 | 01/09 | |
| 0 | Doc fluxo mensal | 2 | 1 | 01/09 | 02/09 | |
| 0 | Teste + deploy | 2 | 1 | 02/09 | 02/09 | |
| 1 | Migration PeriodoAcademia | 3 | 2 | 02/09 | 03/09 | |
| 1 | Migration ItemPeriodoAcademia | 3 | 2 | 03/09 | 03/09 | |
| 1 | Serviço afericao.py | 12 | 6 | 03/09 | 04/09 | |
| 1 | Mapeamento fórmulas | 8 | 5 | 04/09 | 05/09 | |
| 1 | calculos.py | 6 | 3 | 05/09 | 05/09 | |
| 1 | Views recalcular/fechar | 8 | 4 | 05/09 | 06/09 | |
| 1 | Template dashboard | 12 | 6 | 06/09 | 07/09 | |
| 1 | Bonificação atendente | 4 | 2 | 07/09 | 07/09 | |
| 1 | Testes + deploy | 2 | 2 | 08/09 | 08/09 | **MVP** |
| 2 | RegistroCancelamento | 10 | 6 | 09/09 | 10/09 | |
| 2 | LRD diária | 18 | 11 | 10/09 | 12/09 | |
| 2 | AuditoriaSOP | 14 | 8 | 12/09 | 15/09 | |
| 2 | RegistroReclamacao | 10 | 6 | 15/09 | 16/09 | |
| 2 | Painel KPIs | 22 | 13 | 16/09 | 19/09 | |
| 2 | Relatório retenção | 10 | 6 | 19/09 | 22/09 | |
| 2 | Aferição inadimplentes | 8 | 5 | 22/09 | 23/09 | |
| 2 | Testes + deploy | 8 | 5 | 23/09 | 26/09 | **Recepção** |
| 3 | Régua 90d padrinho | 24 | 14 | 26/09 | 01/10 | |
| 3 | Retenção D90 | 16 | 10 | 01/10 | 03/10 | |
| 3 | Avaliações | 12 | 7 | 03/10 | 06/10 | |
| 3 | Ocupação aulas | 10 | 6 | 06/10 | 07/10 | |
| 3 | Comissão vendas | 16 | 10 | 07/10 | 10/10 | |
| 3 | KPIs fechamento | 8 | 5 | 10/10 | 13/10 | |
| 3 | Testes + deploy | 4 | 3 | 13/10 | 24/10 | **Padrinho** |
| 4 | PDF extrato | 12 | 7 | 24/10 | 28/10 | |
| 4 | Multi-unidade | 20 | 11 | 28/10 | 03/11 | |
| 4 | Certificação | 24 | 14 | 03/11 | 10/11 | |
| 4 | NPS estruturado | 8 | 5 | 10/11 | 12/11 | |
| 4 | Stub CRM/check-in | 16 | 8 | 12/11 | 21/11 | **Completo** |

## Bloco CSV (salvar como `cronograma.csv`)

```

---

## Resumo financeiro para a planilha

Premissas: R$ 120/h; dólar a R$ 5,50; custo de tokens estimado; adicional de 30% para variação de uso no Cursor AI.

| Escopo | Horas_Com_IA | Mao_de_Obra_R$ | Tokens_Estimados_M | Tokens_Base_R$ | Cursor_30_R$ | Custo_IA_Total_R$ | Total_Projeto_R$ |
|--------|-------------:|----------------:|--------------------:|----------------:|--------------:|------------------:|-----------------:|
| MVP | 36 | 4.320,00 | 16,4 | 330,00 | 99,00 | 429,00 | 4.749,00 |
| Até recepção | 96 | 11.520,00 | 40,9 | 825,00 | 247,50 | 1.072,50 | 12.592,50 |
| Projeto completo | 200 | 24.000,00 | 81,8 | 1.650,00 | 495,00 | 2.145,00 | 26.145,00 |

### Bloco CSV financeiro

```csv
Escopo,Horas_Com_IA,Mao_de_Obra_BRL,Tokens_Estimados_M,Tokens_Base_BRL,Cursor_30_BRL,Custo_IA_Total_BRL,Total_Projeto_BRL
MVP,36,4320.00,16.4,330.00,99.00,429.00,4749.00
Ate_recepcao,96,11520.00,40.9,825.00,247.50,1072.50,12592.50
Projeto_completo,200,24000.00,81.8,1650.00,495.00,2145.00,26145.00
```
Fase,Tarefa,Horas_Sem_IA,Horas_Com_IA,Inicio,Fim_IA,Marco
0,Menu Meta Academia,2,1,2026-09-01,2026-09-01,
0,Seeds premiação Atendente,3,1,2026-09-01,2026-09-01,
0,Doc fluxo mensal,2,1,2026-09-01,2026-09-02,
0,Teste + deploy,2,1,2026-09-02,2026-09-02,
1,Migration PeriodoAcademia,3,2,2026-09-02,2026-09-03,
1,Migration ItemPeriodoAcademia,3,2,2026-09-03,2026-09-03,
1,Serviço afericao.py,12,6,2026-09-03,2026-09-04,
1,Mapeamento fórmulas,8,5,2026-09-04,2026-09-05,
1,calculos.py,6,3,2026-09-05,2026-09-05,
1,Views recalcular/fechar,8,4,2026-09-05,2026-09-06,
1,Template dashboard,12,6,2026-09-06,2026-09-07,
1,Bonificação atendente,4,2,2026-09-07,2026-09-07,
1,Testes + deploy,2,2,2026-09-08,2026-09-08,MVP
2,RegistroCancelamento,10,6,2026-09-09,2026-09-10,
2,LRD diária,18,11,2026-09-10,2026-09-12,
2,AuditoriaSOP,14,8,2026-09-12,2026-09-15,
2,RegistroReclamacao,10,6,2026-09-15,2026-09-16,
2,Painel KPIs,22,13,2026-09-16,2026-09-19,
2,Relatório retenção,10,6,2026-09-19,2026-09-22,
2,Aferição inadimplentes,8,5,2026-09-22,2026-09-23,
2,Testes + deploy,8,5,2026-09-23,2026-09-26,Recepção
3,Régua 90d,24,14,2026-09-26,2026-10-01,
3,Retenção D90,16,10,2026-10-01,2026-10-03,
3,Avaliações,12,7,2026-10-03,2026-10-06,
3,Ocupação aulas,10,6,2026-10-06,2026-10-07,
3,Comissão vendas,16,10,2026-10-07,2026-10-10,
3,KPIs fechamento,8,5,2026-10-10,2026-10-13,
3,Testes + deploy,4,3,2026-10-13,2026-10-24,Padrinho
4,PDF extrato,12,7,2026-10-24,2026-10-28,
4,Multi-unidade,20,11,2026-10-28,2026-11-03,
4,Certificação,24,14,2026-11-03,2026-11-10,
4,NPS estruturado,8,5,2026-11-10,2026-11-12,
4,Stub CRM,16,8,2026-11-12,2026-11-21,Completo
```
