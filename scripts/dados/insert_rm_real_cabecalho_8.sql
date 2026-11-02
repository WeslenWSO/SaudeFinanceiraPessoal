-- REAL CONVÊNIOS / TABELA REAL — Ressonância (RM)
-- Cabeçalho id=8 (REAL CONVÊNIOS — TABELA REAL)
-- preco_apartamento = sem contraste | preco_enfermaria = com contraste

BEGIN;

-- DELETE FROM servicos_medicos_tabelapreco WHERE cabecalho_id = 8;

-- Serviços médicos
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101316-JOEL', 'RM- JOELHOS', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101316-OMB', 'RM- OMBROS', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101316-QUAD', 'RM- QUADRIL', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101316-TORN', 'RM- TORNOZELO', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101316-PUNH', 'RM- PUNHO', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101316-ANTE', 'RM- ANTEBRACO', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101316-COT', 'RM- COTOVELO', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101316-ESTCL', 'RM- ESTERNO-CLAVICULAR', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101014', 'RM- CRANIO', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101073', 'RM- ORBITAS BILATERAL', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101081', 'RM- OSSOS TEMPORAIS BILATERAIS', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101030', 'RM- BASE DO CRANIO', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101090', 'RM- FACE (INCLUI SEIOS DA FACE)', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101278', 'RM- BACIA (ARTICULACOES SACROILIACAS)', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101120', 'RM- TORAX', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('RM-ABD-TOT', 'RM- ABDOME TOTAL', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101189', 'RM- PELVE', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101170', 'RM- ABDOME SUPERIOR', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101480', 'RM- MAMA BILATERAL', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101111', 'RM- PESCOCO', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101103', 'RM- ARTICULACAO TEMPOROMANDIBULAR BILATERAL', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101197', 'RM- FETAL', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101340', 'ANGIO-RM DE AORTA ABDOMINAL', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101219', 'RM- BOLSA ESCROTAL', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101286', 'RM- COXA', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101260', 'RM- MAO', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101308', 'RM- PE (ANTE PE)', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101227', 'RM- COLUNA CERVICAL, DORSAL OU LOMBAR', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101294', 'RM- PERNA', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101022', 'RM- SELA TURCICA', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101251', 'RM- MEMBRO SUPERIOR UNILATERAL', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101138', 'RM- CARDIACA', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101359-COLANG', 'COLANGIO RM - HIDRO RM', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('RM-DEFECO', 'DEFECORRESSONANCIA', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('RM-ENTERO', 'ENTERORRESONANCIA', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101359-UROR', 'URORRESONANCIA / VIAS URINARIAS', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101065', 'ESPECTROSCOPIA', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101383', 'RECONSTRUCAO 3D RM/TC', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101537', 'ANGIO-RM ARTERIAL DE CRANIO', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101545', 'ANGIO-RM VENOSA DE CRANIO', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101510', 'ANGIO-RM ARTERIAL DE ABDOME SUPERIOR', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101529', 'ANGIO-RM VENOSA DE ABDOME SUPERIOR', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101596', 'ANGIO-RM ARTERIAL DE PELVE', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101600', 'ANGIO-RM VENOSA DE PELVE', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101332', 'ANGIO-RM DA AORTA TORACICA', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;
INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico) VALUES ('41101618', 'ANGIO-RM ARTERIAL DE PESCOCO', NULL) ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;

-- Preços
WITH cab AS (
  SELECT id, empresa_id, convenio_id FROM servicos_medicos_cabecalho WHERE id = 8
),
dados (codigo, sem, com) AS (
  VALUES
    ('41101316-JOEL', 1100.00, 1450.00),
    ('41101316-OMB', 1100.00, 1450.00),
    ('41101316-QUAD', 1100.00, 1450.00),
    ('41101316-TORN', 1100.00, 1450.00),
    ('41101316-PUNH', 1100.00, 1450.00),
    ('41101316-ANTE', 1100.00, 1450.00),
    ('41101316-COT', 1100.00, 1450.00),
    ('41101316-ESTCL', 1100.00, 1450.00),
    ('41101014', 1100.00, 1450.00),
    ('41101073', 1100.00, 1450.00),
    ('41101081', 1100.00, 1450.00),
    ('41101030', 1100.00, 1450.00),
    ('41101090', 1100.00, 1450.00),
    ('41101278', 1100.00, 1450.00),
    ('41101120', 1100.00, 1450.00),
    ('RM-ABD-TOT', 1600.00, 1800.00),
    ('41101189', 1100.00, 1450.00),
    ('41101170', 1100.00, 1450.00),
    ('41101480', 2200.00, 2550.00),
    ('41101111', 1100.00, 1450.00),
    ('41101103', 1100.00, 1450.00),
    ('41101197', 1100.00, 1450.00),
    ('41101340', 1210.00, 1560.00),
    ('41101219', 1100.00, 1450.00),
    ('41101286', 1100.00, 1450.00),
    ('41101260', 1100.00, 1450.00),
    ('41101308', 1100.00, 1450.00),
    ('41101227', 1100.00, 1450.00),
    ('41101294', 1100.00, 1450.00),
    ('41101022', 1100.00, 1450.00),
    ('41101251', 1100.00, 1450.00),
    ('41101138', 2500.00, 2900.00),
    ('41101359-COLANG', 1600.00, 1800.00),
    ('RM-DEFECO', 2550.00, 2750.00),
    ('RM-ENTERO', 2550.00, 2750.00),
    ('41101359-UROR', 1600.00, 1800.00),
    ('41101065', 250.00, 250.00),
    ('41101383', 150.00, 150.00),
    ('41101537', 1210.00, 1560.00),
    ('41101545', 1210.00, 1560.00),
    ('41101510', 1210.00, 1560.00),
    ('41101529', 1210.00, 1560.00),
    ('41101596', 1210.00, 1560.00),
    ('41101600', 1210.00, 1560.00),
    ('41101332', 1210.00, 1560.00),
    ('41101618', 1210.00, 1560.00)
)
INSERT INTO servicos_medicos_tabelapreco (
  empresa_id, convenio_id, cabecalho_id, codigo_servico_id,
  preco_apartamento, preco_enfermaria
)
SELECT
  cab.empresa_id, cab.convenio_id, cab.id, s.id, d.sem, d.com
FROM dados d
JOIN servicos_medicos_servicosmedicos s ON s.codigo = d.codigo
CROSS JOIN cab
ON CONFLICT (empresa_id, convenio_id, cabecalho_id, codigo_servico_id) DO UPDATE SET
  preco_apartamento = EXCLUDED.preco_apartamento,
  preco_enfermaria = EXCLUDED.preco_enfermaria;

COMMIT;