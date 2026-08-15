from django.urls import path
from . import views

app_name = 'faturamento_medico'

urlpatterns = [
    path('', views.listar_faturamentos, name='ftlistar'),
    path('cancelados/', views.listar_cancelados, name='listar_cancelados'),
    path('exames-por-solicitante/', views.listar_exames_por_solicitante, name='listar_exames_por_solicitante'),
    path('verificar-corrigir-precos/', views.verificar_corrigir_precos, name='verificar_corrigir_precos'),
    path('criar/', views.criar_faturamento, name='criar'),
    path('<int:pk>/editar/', views.editar_faturamento, name='editar'),
    path('<int:pk>/editar-documentacao/', views.editar_documentacao_faturamento, name='editar_documentacao'),
    path('<int:pk>/excluir/', views.excluir_faturamento, name='excluir'),
    path('<int:pk>/detalhes/', views.detalhes_faturamento, name='detalhes'),
    path('exportar-excel/', views.exportar_excel, name='exportar_excel'),
    path('gerar-lote/', views.gerar_lote, name='gerar_lote'),
    path('vincular-lote-protocolo/', views.vincular_lote_protocolo, name='vincular_lote_protocolo'),
    # URLs para documentos anexados
    path('<int:pk>/anexar-documento/', views.anexar_documento, name='anexar_documento'),
    path('documento/<int:pk>/download/', views.download_documento, name='download_documento'),
    path('documento/<int:pk>/excluir/', views.excluir_documento, name='excluir_documento'),

    # URLs para itens de serviço
    path('<int:pk>/adicionar-item/', views.adicionar_item_servico, name='adicionar_item_servico'),
    path('item/<int:pk>/editar/', views.editar_item_servico, name='editar_item_servico'),
    path('item/<int:pk>/excluir/', views.excluir_item_servico, name='excluir_item_servico'),

    # URL para fechamento de repasse
    path('fechamento-repasse/', views.fechamento_repasse, name='fechamento_repasse'),
    path('reabrir-fechamento/<int:pk>/', views.reabrir_fechamento, name='reabrir_fechamento'),
    path('exportar-excel-fechados/', views.exportar_excel_fechados, name='exportar_excel_fechados'),

    # URLs para serviços disponíveis
    path('servicos/', views.listar_servicos, name='listar_servicos'),
    path('servicos/criar/', views.criar_servico, name='criar_servico'),
    path('servicos/<int:pk>/editar/', views.editar_servico, name='editar_servico'),
    path('extrair-dados/', views.extrair_dados_documento, name='extrair_dados'),
    path('extrair-dados-ocr/', views.extrair_dados_documento_ocr, name='extrair_dados_ocr'),
    path('servicos/<int:pk>/excluir/', views.excluir_servico, name='excluir_servico'),

    path('imprimir-lote/', views.selecionar_lote_imprimir, name='selecionar_lote_imprimir'),
    path('imprimir-lote/<int:lote_id>/', views.imprimir_lote, name='imprimir_lote'),
    path(
        'imprimir-lote-convenio-publico/<int:lote_id>/',
        views.imprimir_lote_convenio_publico,
        name='imprimir_lote_convenio_publico',
    ),
    path('imprimir-repasses-fechados/', views.imprimir_repasses_fechados, name='imprimir_repasses_fechados'),

    # AJAX
    path('ajax/carregar-tabelas/<int:cabecalho_id>/', views.carregar_tabelas_por_cabecalho, name='carregar_tabelas_por_cabecalho'),
    path('ajax/carregar-precos/<int:cabecalho_id>/', views.carregar_precos_por_cabecalho, name='carregar_precos_por_cabecalho'),
    path('ajax/buscar-servicos/', views.buscar_servicos, name='buscar_servicos'),
    path('ajax/buscar-servicos-descricao/', views.buscar_servicos_por_descricao, name='buscar_servicos_por_descricao'),
    path('ajax/buscar-precos-servico/<int:cabecalho_id>/<str:codigo_servico>/', views.buscar_precos_servico, name='buscar_precos_servico'),

    # Import
    path('importar-unimed/', views.importar_unimed, name='importar_unimed'),
    path('importar-xml/', views.importar_xml, name='importar_xml'),
    path('importar-ris/', views.importar_ris, name='importar_ris'),
    path('sincronizar-medcloud/', views.sincronizar_medcloud, name='sincronizar_medcloud'),
    path('importar-extrato-pagamento-bradesco/', views.importar_extrato_pagamento_bradesco, name='importar_extrato_pagamento_bradesco'),
    path('extrato-pagamento/', views.listar_extrato_pagamento, name='listar_extrato_pagamento'),
    path('extrato-pagamento/<int:pk>/editar/', views.editar_extrato_pagamento, name='editar_extrato_pagamento'),
    path('extrato-pagamento/<int:pk>/baixar/', views.baixar_extrato_pagamento, name='baixar_extrato_pagamento'),
    path('extrato-pagamento/<int:pk>/estornar-baixa/', views.estornar_baixa_extrato_pagamento, name='estornar_baixa_extrato_pagamento'),
    path('modelo-ris/', views.baixar_modelo_ris, name='baixar_modelo_ris'),
    path('item/<int:pk>/lancar-glosa/', views.lancar_glosa_item, name='lancar_glosa_item'),
    path('item/<int:pk>/conferencia/', views.toggle_conferencia_item, name='toggle_conferencia'),
    path('item/<int:pk>/status-conferencia/', views.alterar_status_conferencia_item, name='alterar_status_conferencia'),
]