-- Script para corrigir KeyError ('contasareceber', 'baixacontaareceber') no servidor MySQL
-- Execute no banco de PRODUÇÃO. Depois rode no servidor: python manage.py migrate
--
-- O que faz: remove o registro da migration 0009 da tabela django_migrations.
-- O Django vai reaplicar a 0009 na ordem correta (depois da 0003).
--
-- ATENÇÃO: Faça backup do banco antes (mysqldump).

-- Troque NOME_DO_BANCO pelo nome real (ex: saude_financeira)
-- USE NOME_DO_BANCO;

DELETE FROM django_migrations 
WHERE app = 'contasareceber' 
  AND name = '0009_fix_foreign_key_alter_field';

-- Para conferir o nome exato da migration no servidor:
-- SELECT id, app, name FROM django_migrations WHERE app = 'contasareceber' ORDER BY id;
