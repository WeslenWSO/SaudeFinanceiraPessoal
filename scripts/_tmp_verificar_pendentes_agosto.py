from faturamento_medico.dashboard_exames import montar_dashboard_exames

empresa_id = 16
for ano, mes in [(2026, 8), (2025, 8), (2024, 8)]:
    d = montar_dashboard_exames(empresa_id, ano, mes)
    pend = next(
        (x for x in d['totais_gerais']['status_linhas'] if x['status'] == 'PENDENTE'),
        None,
    )
    print('=== %s (%s a %s) ===' % (d['mes_label'], d['data_inicio'], d['data_fim']))
    if pend:
        print('PENDENTE: qtd=%s valor=%s' % (pend['quantidade'], pend['valor']))
    else:
        print('PENDENTE: 0')
    print('Total: qtd=%s valor=%s' % (
        d['totais_gerais']['total_quantidade'],
        d['totais_gerais']['total_valor'],
    ))
    print()
