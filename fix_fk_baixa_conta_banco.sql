-- Corrige FK de contasareceber_baixacontaareceber.conta_banco_id
-- Erro 1452: FK apontava para contabanco_contabanco (inexistente)
-- Deve referenciar extrato_contabancaria(id)
-- Execute no MySQL: mysql -u usuario -p saude_financeira < fix_fk_baixa_conta_banco.sql

SET FOREIGN_KEY_CHECKS = 0;

ALTER TABLE contasareceber_baixacontaareceber
DROP FOREIGN KEY contasareceber_baixa_conta_banco_id_f462de09_fk_contabanc;

ALTER TABLE contasareceber_baixacontaareceber
ADD CONSTRAINT fk_baixa_conta_banco_extrato
FOREIGN KEY (conta_banco_id) REFERENCES extrato_contabancaria(id);

SET FOREIGN_KEY_CHECKS = 1;
