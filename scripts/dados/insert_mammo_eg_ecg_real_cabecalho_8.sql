-- 5 exames | MAMO + EEG + ECG | convenio_id=5 | cabecalho_id=8 | empresa_id=1

BEGIN;

INSERT INTO servicos_medicos_servicosmedicos (codigo, servicos, porte_anestesico)
SELECT codigo, nome, NULL FROM (VALUES
  ('40808033', 'MAMOGRAFIA DIGITAL'),
  ('40808050', 'COMPRESSAO SELETIVA MAMA'),
  ('40103846', 'ELETROENCEFALOGRAMA'),
  ('40103846-SED', 'ELETROENCEFALOGRAMA C/ SEDACAO'),
  ('40101010', 'ELETROCARDIOGRAMA')
) AS t(codigo, nome)
ON CONFLICT (codigo) DO UPDATE SET servicos = EXCLUDED.servicos;

INSERT INTO servicos_medicos_tabelapreco
  (empresa_id, convenio_id, cabecalho_id, codigo_servico_id, preco_apartamento, preco_enfermaria)
SELECT 1, 5, 8, s.id, v.valor, v.valor
FROM (VALUES
  ('40808033', 280.00),
  ('40808050', 560.00),
  ('40103846', 300.00),
  ('40103846-SED', 950.00),
  ('40101010', 300.00)
) AS v(codigo, valor)
JOIN servicos_medicos_servicosmedicos s ON s.codigo = v.codigo
ON CONFLICT (empresa_id, convenio_id, cabecalho_id, codigo_servico_id)
DO UPDATE SET
  preco_apartamento = EXCLUDED.preco_apartamento,
  preco_enfermaria = EXCLUDED.preco_enfermaria;

COMMIT;
