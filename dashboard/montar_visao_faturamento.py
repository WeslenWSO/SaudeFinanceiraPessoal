"""Visão Faturamento no dashboard principal — gráfico por categoria (convênio)."""

from __future__ import annotations

import json

from dashboard.analise_faturamento_convenio import montar_relatorio_faturamento_convenio


def montar_visao_faturamento(empresa_id: int, ano: int, mes: int) -> dict:
    rel = montar_relatorio_faturamento_convenio(empresa_id, ano, mes)
    linhas = rel.get('linhas_convenio') or []
    labels = [row['convenio'] for row in linhas]
    valores = [float(row['valor']) for row in linhas]
    total = sum(valores)

    return {
        **rel,
        'tem_dados': total > 0,
        'chart_categoria_labels_json': json.dumps(labels, ensure_ascii=False),
        'chart_categoria_data_json': json.dumps(valores),
        'total_valor_num': total,
    }
