"""Gera CSV FUSEX jul/2026 a partir da planilha enviada ao convênio."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'scripts' / 'dados' / 'fusex_conferencia_jul2026.csv'

# data, paciente, guia, procedimento, mod, valor
ROWS = [
    # --- imagem 1 (01–14/jul) ---
    ('01/07/2026', 'MARIA JOSE DE LIMA CUNHA', '202610024', 'RM - COLUNA DORSAL', 'MR', '856,10'),
    ('01/07/2026', 'MARIA JOSE DE LIMA CUNHA', '202610024', 'RM - COLUNA LOMBAR', 'MR', '856,10'),
    ('01/07/2026', 'MARIA JOSE DE LIMA CUNHA', '202610024', 'RM - Articular (por articulação)', 'MR', '856,10'),
    ('01/07/2026', 'MARIA ROZENIR DE FREITAS LIMA', '202610029', 'TC - Coluna cervical ou dorsal ou lombo-sacra', 'CT', '359,26'),
    ('01/07/2026', 'MARIA ROZENIR DE FREITAS LIMA', '202610029', 'TC - Coluna cervical ou dorsal ou lombo-sacra', 'CT', '359,26'),
    ('01/07/2026', 'MARIA ROZENIR DE FREITAS LIMA', '202610029', 'TC - Coluna cervical ou dorsal ou lombo-sacra', 'CT', '359,26'),
    ('02/07/2026', 'RAIANY ABREU DE OLIVEIRA', '202610261', 'TC - Tórax', 'CT', '471,96'),
    ('03/07/2026', 'FLAVIA FIGUEIRA MORAIS', '202610206', 'MAMOGRAFIA DIGITAL', 'MG', '186,38'),
    ('04/07/2026', 'BERNARDO TELES MEIRELES DANTAS', '20269891', 'RX ADENOIDES OU CAVUM', 'CR', '39,50'),
    ('04/07/2026', 'SCHARINE BONDAN', '20268575', 'RX - JOELHO ESQUERDO', 'CR', '44,83'),
    ('04/07/2026', 'SCHARINE BONDAN', '20268575', 'RX JOELHO DIREITO', 'CR', '44,83'),
    ('04/07/2026', 'SCHARINE BONDAN', '20268575', 'RX BACIA', 'CR', '42,83'),
    ('04/07/2026', 'SCHARINE BONDAN', '20268575', 'RX COLUNA TOTAL PANORAMICA', 'CR', '139,84'),
    ('08/07/2026', 'LUIZ ANTONIO DE ARAUJO', '202610519', 'RM - Articular (por articulação)', 'MR', '856,10'),
    ('08/07/2026', 'LUIZ ANTONIO DE ARAUJO', '202610519', 'RM - COLUNA CERVICAL', 'MR', '856,10'),
    ('08/07/2026', 'LUAN PEKLY DE ASSIS BARROZO', '202610576', 'RM - JOELHO DIREITO', 'MR', '856,10'),
    ('08/07/2026', 'LUAN PEKLY DE ASSIS BARROZO', '202610576', 'RM - JOELHO ESQUERDO', 'MR', '856,10'),
    ('08/07/2026', 'LUAN PEKLY DE ASSIS BARROZO', '202610576', 'RM - Articular (por articulação)', 'MR', '856,10'),
    ('08/07/2026', 'ANTONIO WELLINGTON RIBEIRO DE OLIVEIRA', '20268265', 'RX TORAX 2 INCIDENCIA', 'CR', '46,21'),
    ('08/07/2026', 'GERALDO JORGE DAMASCENO', '202610582', 'TC - Abdome total', 'CT', '1431,80'),
    ('09/07/2026', 'GILVANEIA DE ALMADA FERREIRA', '202610674', 'RM - COLUNA LOMBAR COM CONTRASTE', 'MR', '1596,30'),
    ('09/07/2026', 'VICENTE LIMA DA SILVA', '202610832', 'RX TORAX 2 INCIDENCIA', 'CR', '46,21'),
    ('09/07/2026', 'CARLOS SERGIO SILVA SANTOS', '202610731', 'RM - Crânio (encéfalo) Com Contraste', 'MR', '1596,30'),
    ('09/07/2026', 'ERICA TELLES POVOA DA CRUZ', '202610783', 'Hidro-RM', 'MR', '1596,30'),
    ('10/07/2026', 'MARLI LIRA FERREIRA', '202610628', 'RM - Bacia (articulações sacroilíacas)', 'MR', '856,10'),
    ('10/07/2026', 'MARLI LIRA FERREIRA', '202610628', 'RM - COLUNA LOMBAR', 'MR', '856,10'),
    ('10/07/2026', 'MARLI LIRA FERREIRA', '202610628', 'RM - COLUNA DORSAL', 'MR', '856,10'),
    ('10/07/2026', 'MARLI LIRA FERREIRA', '202610628', 'RM - COLUNA CERVICAL', 'MR', '856,10'),
    ('11/07/2026', 'MARLI LIRA FERREIRA', '202610629', 'MAMOGRAFIA DIGITAL', 'MG', '186,38'),
    ('11/07/2026', 'MARLI LIRA FERREIRA', '202610629', 'RM - Crânio (encéfalo) Com Contraste', 'MR', '1596,20'),
    ('10/07/2026', 'JOAO GUARACU RODRIGUES DE QUADROS', '202610907', 'RX OMBRO ESQUERDO', 'CR', '42,28'),
    ('10/07/2026', 'JOAO GUARACU RODRIGUES DE QUADROS', '202610907', 'RX OMBRO DIREITO', 'CR', '42,28'),
    ('10/07/2026', 'JOAO GUARACU RODRIGUES DE QUADROS', '202610907', 'RM - Articular (por articulação)', 'MR', '856,10'),
    ('10/07/2026', 'JOAO GUARACU RODRIGUES DE QUADROS', '202610907', 'RM - Articular (por articulação)', 'MR', '856,10'),
    ('11/07/2026', 'CARLOS HENRIQUE DOS SANTOS SANTANA', '202610648', 'TC - Coluna cervical ou dorsal ou lombo-sacra', 'CT', '359,26'),
    ('11/07/2026', 'CARLOS HENRIQUE DOS SANTOS SANTANA', '202610648', 'TC - Coluna cervical ou dorsal ou lombo-sacra', 'CT', '370,05'),
    ('11/07/2026', 'CARLOS HENRIQUE DOS SANTOS SANTANA', '202610648', 'TC - Coluna cervical ou dorsal ou lombo-sacra', 'CT', '370,05'),
    ('13/07/2026', 'ANTONIA RIBEIRO FERNANDES LIMA', '20268727', 'US - TIREOIDE COM DOPPLER', 'US', '234,66'),
    ('13/07/2026', 'ANTONIA RIBEIRO FERNANDES LIMA', '20268727', 'Doppler colorido de vasos cervicais arteriais bilateral', 'US', '370,10'),
    ('13/07/2026', 'ANTONIA RIBEIRO FERNANDES LIMA', '20268727', 'US - TRANSVAGINAL', 'US', '114,77'),
    ('13/07/2026', 'ANTONIA RIBEIRO FERNANDES LIMA', '20268727', 'US - Abdome total', 'US', '196,15'),
    ('13/07/2026', 'ANTONIA RIBEIRO FERNANDES LIMA', '20268727', 'US - Mamas', 'US', '113,90'),
    ('13/07/2026', 'EUDI FRANQUIO ARAUJO DA SILVA', '20269835', 'US - Próstata (via abdominal)', 'US', '118,06'),
    ('14/07/2026', 'MARIA JOSE DE LIMA CUNHA', '202610031', 'RX - JOELHO ESQUERDO', 'CR', '44,83'),
    ('14/07/2026', 'MARIA JOSE DE LIMA CUNHA', '202610031', 'RX JOELHO DIREITO', 'CR', '44,83'),
    ('14/07/2026', 'MARIA JOSE DE LIMA CUNHA', '202610031', 'RX BACIA', 'CR', '42,83'),
    ('14/07/2026', 'MARIA JOSE DE LIMA CUNHA', '202610031', 'RX COLUNA LOMBAR', 'CR', '49,15'),
    ('14/07/2026', 'MARIA JOSE DE LIMA CUNHA', '202610031', 'RX COLUNA DORSAL', 'CR', '47,32'),
    ('14/07/2026', 'MARIA JOSE DE LIMA CUNHA', '202610031', 'RX COLUNA CERVICAL', 'CR', '43,37'),
    # --- imagem 2 (14–23/jul) ---
    ('14/07/2026', 'RENATO CORREA DA SILVA', '202610574', 'RX TORNOZELO ESQUERDO', 'CR', '41,12'),
    ('14/07/2026', 'RENATO CORREA DA SILVA', '202610574', 'RM - Articular (por articulação)', 'MR', '856,10'),
    ('14/07/2026', 'DIANA PAULA DE ABREU TAVARES', '202610624', 'US - OBSTETRICA COM DOPPLER', 'US', '240,92'),
    ('15/07/2026', 'MARIA MARLUCE LIMA DO NASCIMENTO', '202611116', 'TC - Pelve ou bacia', 'CT', '471,96'),
    ('15/07/2026', 'FARIDES CAMELI SANTIAGO', '202611108', 'RM - JOELHO ESQUERDO', 'MR', '856,10'),
    ('15/07/2026', 'FARIDES CAMELI SANTIAGO', '202611108', 'RM - Articular (por articulação)', 'MR', '856,10'),
    ('15/07/2026', 'FARIDES CAMELI SANTIAGO', '202611109', 'RX BACIA', 'CR', '42,83'),
    ('15/07/2026', 'FARIDES CAMELI SANTIAGO', '202611109', 'RX PATELA', 'CR', '44,83'),
    ('15/07/2026', 'FARIDES CAMELI SANTIAGO', '202611109', 'RX - JOELHO ESQUERDO', 'CR', '44,83'),
    ('15/07/2026', 'MARIA RAIMUNDA PINHEIRO', '202610323', 'MAMOGRAFIA DIGITAL', 'MG', '186,38'),
    ('16/07/2026', 'MARIA RAIMUNDA PINHEIRO', '202610323', 'US - Estruturas superficiais', 'US', '189,70'),
    ('16/07/2026', 'MARIA RAIMUNDA PINHEIRO', '202610323', 'US - Mamas', 'US', '113,90'),
    ('16/07/2026', 'YASMIN VITORIA PEREIRA DA SILVA', '20269657', 'US - Órgãos superficiais', 'US', '94,85'),
    ('17/07/2026', 'INGRID NATSCHA DE SOUZA SAMPAIO', '20269848', 'US - Transvaginal p/ pesquisa', 'US', '114,77'),
    ('17/07/2026', 'ISABELE DA SILVA GONCALVES', '202611167', 'TC - Abdome total', 'CT', '691,70'),
    ('17/07/2026', 'MADALENA GOMES FREIRES', '202611183', 'US - TRANSVAGINAL', 'US', '114,77'),
    ('20/07/2026', 'DIEGO YUSSEF DE LIMA FRANCO', '202611352', 'RM - Articular (por articulação)', 'MR', '856,10'),
    ('20/07/2026', 'DIEGO YUSSEF DE LIMA FRANCO', '202611352', 'RM - JOELHO DIREITO', 'MR', '856,10'),
    ('20/07/2026', 'ANA CAROLINA DUARTE VIANNAY', '202610425', 'US - TRANSVAGINAL', 'US', '114,77'),
    ('21/07/2026', 'DIEGO YUSSEF DE LIMA FRANCO', '202611351', 'RX BACIA', 'CR', '42,83'),
    ('21/07/2026', 'DIEGO YUSSEF DE LIMA FRANCO', '202611351', 'RX PANORAMICA MEMBROS INF.', 'CR', '76,34'),
    ('21/07/2026', 'DIEGO YUSSEF DE LIMA FRANCO', '202611351', 'RX JOELHO DIREITO', 'CR', '44,83'),
    ('21/07/2026', 'DIEGO YUSSEF DE LIMA FRANCO', '202611351', 'RX PATELA', 'CR', '44,83'),
    ('21/07/2026', 'LOHANA NASCIMENTO DOS SANTOS', '202610947', 'US - OBSTETRICA COM DOPPLER', 'US', '84,90'),
    ('21/07/2026', 'LOHANA NASCIMENTO DOS SANTOS', '202610947', 'DOPPLER COLORIDO ORGÃO', 'US', '234,66'),
    ('21/07/2026', 'LOHANA NASCIMENTO DOS SANTOS', '202610947', 'US - Obstétrica morfológica', 'US', '400,00'),
    ('21/07/2026', 'MARIA ELIANE DE AZEVEDO ZUMBA', '202610974', 'US - Órgãos superficiais', 'US', '94,85'),
    ('21/07/2026', 'MARIA ELIANE DE AZEVEDO ZUMBA', '202610974', 'US - Abdome total', 'US', '196,15'),
    ('21/07/2026', 'MANOEL FELIPE SANTIAGO NETO', '202610861', 'RM - ABDOME TOTAL COM CONTRASTE', 'MR', '2498,03'),
    ('22/07/2026', 'LUISA KAROLAYNE SILVA DE SOUZA', '202611396', 'US - Articular (por articulação)', 'US', '118,55'),
    ('22/07/2026', 'MARIA JOSE CORREA', '20269899', 'MAMOGRAFIA DIGITAL', 'MG', '186,38'),
    ('22/07/2026', 'MARIA JOSE CORREA', '20269899', 'US - Estruturas superficiais', 'US', '94,85'),
    ('22/07/2026', 'MARIA JOSE CORREA', '20269899', 'US - Mamas', 'US', '113,90'),
    ('22/07/2026', 'MARIA JOSE DE LIMA CUNHA', '202611453', 'US - TRANSVAGINAL', 'US', '114,77'),
    ('22/07/2026', 'MARIA JOSE DE LIMA CUNHA', '202611453', 'US - TIREOIDE COM DOPPLER', 'US', '94,85'),
    ('22/07/2026', 'MARIA JOSE DE LIMA CUNHA', '202611453', 'DOPPLER COLORIDO ORGAO', 'US', '234,66'),
    ('22/07/2026', 'MARLI LIRA FERREIRA', '202610629', 'US - Articular (por articulação)', 'US', '118,56'),
    ('22/07/2026', 'ROSA DA SILVA PINHEIRO', '202611445', 'RM - JOELHO ESQUERDO', 'MR', '856,10'),
    ('22/07/2026', 'ROSA DA SILVA PINHEIRO', '202611445', 'RX - JOELHO ESQUERDO', 'CR', '44,83'),
    ('22/07/2026', 'ROSA DA SILVA PINHEIRO', '202611445', 'RX JOELHO DIREITO', 'CR', '44,83'),
    ('22/07/2026', 'ROSA DA SILVA PINHEIRO', '202611445', 'RX BACIA', 'CR', '42,83'),
    ('23/07/2026', 'IRENE SOUSA DA SILVA', '202611454', 'RM - COLUNA LOMBAR', 'MR', '856,10'),
    ('23/07/2026', 'IRENE SOUSA DA SILVA', '202611454', 'RM - Crânio (encéfalo)', 'MR', '856,10'),
    # --- imagem 3 (23–31/jul) ---
    ('23/07/2026', 'MARIA ROQUE DE OLIVEIRA', '202610408', 'RX - JOELHO ESQUERDO', 'CR', '44,83'),
    ('23/07/2026', 'MARIA ROQUE DE OLIVEIRA', '202610408', 'RX JOELHO DIREITO', 'CR', '44,83'),
    ('29/07/2026', 'MARIA ROQUE DE OLIVEIRA', '202610408', 'US - Articular (por articulação)', 'US', '118,55'),
    ('29/07/2026', 'MARIA ROQUE DE OLIVEIRA', '202610408', 'US - Articular (por articulação)', 'US', '118,55'),
    ('23/07/2026', 'RENATO CORREA DA SILVA', '202610694', 'US - PARTES MOLES', 'US', '94,85'),
    ('23/07/2026', 'RENATO CORREA DA SILVA', '202610694', 'US - BOLSA ESCROTAL COM DOPPLER', 'US', '234,66'),
    ('23/07/2026', 'RENATO CORREA DA SILVA', '202610694', 'US - Próstata (via abdominal)', 'US', '118,06'),
    ('23/07/2026', 'RENATO CORREA DA SILVA', '202610694', 'US - Abdome total', 'US', '196,15'),
    ('23/07/2026', 'RENATO CORREA DA SILVA', '202610694', 'US - Órgãos superficiais', 'US', '94,85'),
    ('23/07/2026', 'RUTE LEITE RODRIGUES MARTINS', '20269832', 'US - Mamas', 'US', '113,90'),
    ('23/07/2026', 'RUTE LEITE RODRIGUES MARTINS', '20269832', 'US - TRANSVAGINAL', 'US', '114,77'),
    ('23/07/2026', 'RUTE LEITE RODRIGUES MARTINS', '20269832', 'US - Abdome total', 'US', '196,15'),
    ('23/07/2026', 'RUTE LEITE RODRIGUES MARTINS', '20269832', 'US - TIREOIDE COM DOPPLER', 'US', '234,66'),
    ('23/07/2026', 'RUTE LEITE RODRIGUES MARTINS', '20269832', 'US - Orgaos superficiais', 'US', '94,85'),
    ('24/07/2026', 'PEDRO ESTEVAM UCHOA', '202611420', 'TC - Tórax', 'CT', '471,96'),
    ('24/07/2026', 'BRUNNA FERNANDA DE SOUZA MOREIRA', '202610211', 'US - Aparelho urinário', 'US', '191,61'),
    ('24/07/2026', 'BRUNNA FERNANDA DE SOUZA MOREIRA', '202610211', 'US - Abdome total', 'US', '196,15'),
    ('27/07/2026', 'GUSTAVO NOGUEIRA HILARIO MARTINS', '202611464', 'TC - Tórax', 'CT', '471,96'),
    ('27/07/2026', 'EDUARDO MAIA DE BRITO', '202611082', 'RM - JOELHO ESQUERDO', 'MR', '856,10'),
    ('27/07/2026', 'EDUARDO MAIA DE BRITO', '202611082', 'RM - JOELHO DIREITO', 'MR', '856,10'),
    ('27/07/2026', 'EDUARDO MAIA DE BRITO', '202611082', 'RM - Bacia Com Contraste', 'MR', '1596,20'),
    ('27/07/2026', 'EDUARDO MAIA DE BRITO', '202611082', 'RM - Pelve', 'MR', '901,83'),
    ('29/07/2026', 'SAMILLY BARBOSA DA SILVA', '202610149', 'US - Obstétrica morfológica', 'US', '400,00'),
    ('31/07/2026', 'MAYRA DOS SANTOS DE ANDRADE', '202610972', 'US - TRANSVAGINAL', 'US', '114,77'),
    ('31/07/2026', 'MAYRA DOS SANTOS DE ANDRADE', '202610972', 'US - Abdome total', 'US', '196,15'),
    ('31/07/2026', 'MAYRA DOS SANTOS DE ANDRADE', '202610972', 'US - Mamas', 'US', '113,90'),
    ('31/07/2026', 'MAYRA DOS SANTOS DE ANDRADE', '202610972', 'US - TIREOIDE COM DOPPLER', 'US', '329,51'),
    ('31/07/2026', 'MARIA REGIANE ASIS DE ABREU', '20269642', 'US - TIREOIDE COM DOPPLER', 'US', '94,85'),
    ('31/07/2026', 'NEUZA MIRANDA DE FARIAS', '202611522', 'US - Abdome total', 'US', '196,15'),
]


def parse_valor(s: str) -> Decimal:
    s = s.replace('R$', '').strip().replace('.', '').replace(',', '.')
    return Decimal(s)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = ['DATA;PACIENTE;GUIA;PROCEDIMENTO;MODALIDADE;VALOR']
    total = Decimal('0')
    for row in ROWS:
        lines.append(';'.join(row))
        total += parse_valor(row[5])
    OUT.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'Linhas: {len(ROWS)}')
    print(f'Total CSV: R$ {total:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'))
    print(f'Arquivo: {OUT}')
    esperado = Decimal('47822.40')
    print(f'Esperado planilha: R$ {esperado}')
    print(f'Diferença: R$ {total - esperado}')


if __name__ == '__main__':
    main()
