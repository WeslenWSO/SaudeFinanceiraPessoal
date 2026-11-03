-- Rode no DBeaver ANTES do insert FUSEX (copie cabecalho_id e convenio_id corretos)

-- 1) Cabeçalhos FUSEX por empresa
SELECT
  c.id AS cabecalho_id,
  c.nome_tabela,
  c.empresa_id,
  v.id AS convenio_id,
  v.nome AS convenio,
  COUNT(tp.id) AS qtd_precos
FROM servicos_medicos_cabecalho c
JOIN servicos_medicos_convenio v ON v.id = c.convenio_id
LEFT JOIN servicos_medicos_tabelapreco tp
  ON tp.cabecalho_id = c.id AND tp.empresa_id = c.empresa_id
WHERE v.nome ILIKE '%FUSEX%'
   OR c.nome_tabela ILIKE '%FUSEX%'
GROUP BY c.id, c.nome_tabela, c.empresa_id, v.id, v.nome
ORDER BY c.empresa_id, c.id;

-- 2) Confere id=3 / conv=14 / empresa=1 (ajuste se a linha 1 mostrar outros ids)
SELECT c.id, c.nome_tabela, c.empresa_id, v.id AS convenio_id, v.nome
FROM servicos_medicos_cabecalho c
JOIN servicos_medicos_convenio v ON v.id = c.convenio_id
WHERE c.id = 3;

-- 3) Amostra de serviço (precisa existir para gravar preço)
SELECT id, codigo, servicos FROM servicos_medicos_servicosmedicos
WHERE codigo = '40801012';
