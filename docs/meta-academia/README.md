# Meta Academia — Projeto Blue 7K

Documentação de planejamento do módulo **Meta Academia** (app `indicadores`), alinhado aos manuais de treinamento e SOPs da recepção.

**Cliente / referência:** Bluefit Maceió (Projeto Blue 7K)  
**Sistema:** Saúde Financeira Pessoal — Django  
**Início sugerido:** 01/09/2026

## Índice

| Arquivo | Conteúdo |
|---------|----------|
| [01-plano-geral.md](01-plano-geral.md) | Visão, contexto atual, aferição de meta mensal |
| [02-cronograma-resumo.md](02-cronograma-resumo.md) | Horas e prazos — sem IA vs. com IA |
| [03-cronograma-detalhado.md](03-cronograma-detalhado.md) | Tarefas e horas por fase |
| [04-marcos-entrega.md](04-marcos-entrega.md) | Datas de go-live e critérios de pronto |
| [05-fases-implementacao.md](05-fases-implementacao.md) | Escopo técnico de cada fase |
| [06-cronograma-planilha.md](06-cronograma-planilha.md) | Tabela + CSV para Excel/Sheets |

## Referências externas

- `CLIENTES/ACADEMIA/03_Treinamento_Implantacao_por_Setor.docx`
- `CLIENTES/ACADEMIA/04_Scripts_Recepcao_7_SOPs.docx`

## Código relacionado

- `indicadores/` — models, views, services
- `templates/indicadores/` — telas
- `usuario/menu.py` — menu Meta Academia

## Totais rápidos (com IA + Cursor)

| Escopo | Horas | Prazo (~6 h/dia) | Mão de obra | Tokens + 30% Cursor | Total estimado |
|--------|------:|------------------|-------------:|--------------------:|---------------:|
| MVP (Fases 0+1) | ~36 h | ~1 semana | R$ 4.320,00 | R$ 429,00 | **R$ 4.749,00** |
| Até recepção (0+1+2) | ~96 h | ~3 semanas | R$ 11.520,00 | R$ 1.072,50 | **R$ 12.592,50** |
| Projeto completo | ~200 h | ~1,5 mês | R$ 24.000,00 | R$ 2.145,00 | **R$ 26.145,00** |

Estimativa de IA calculada com custo de tokens, câmbio de R$ 5,50/US$ e reserva de 30%. Ver premissas e fórmula em [02-cronograma-resumo.md](02-cronograma-resumo.md).
