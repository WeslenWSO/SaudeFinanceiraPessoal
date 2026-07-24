# Tratamento de Duplicatas na Importação de NFSe

## Problema Resolvido

O erro `(1062, "Duplicate entry '1-406' for key 'notasfiscais_notafiscalservico.notasfiscais_notafiscals_empresa_id_numero_nota_b6f3210d_uniq'")` ocorria quando tentávamos importar XMLs que continham notas fiscais que já existiam no banco de dados.

## Solução Implementada

### 1. Verificação de Duplicatas
- Antes de salvar uma nota fiscal, o sistema verifica se já existe uma nota com a mesma combinação de `empresa` e `numero_nota`
- Se a nota já existe, ela é ignorada e não causa erro

### 2. Relatório Detalhado
- O sistema agora retorna um relatório completo da importação
- Mostra quantas notas foram importadas, ignoradas e processadas
- Lista detalhadamente cada nota ignorada com o motivo

### 3. Mensagens Informativas
- Mensagens de sucesso para notas importadas
- Mensagens de aviso para notas ignoradas
- Diferenciação entre duplicatas e outros tipos de erro

## Como Funciona

### Estrutura do Retorno
```python
{
    'nfses': [lista_de_objetos_nfse_criados],
    'notas_importadas': [
        {
            'numero_nota': '1-407',
            'cliente': 'Cliente Teste',
            'valor_liquido': Decimal('2000.00')
        }
    ],
    'notas_ignoradas': [
        {
            'numero_nota': '1-406',
            'cliente': 'Cliente Existente',
            'motivo': 'Nota já existe no banco'
        }
    ],
    'total_processadas': 2,
    'total_importadas': 1,
    'total_ignoradas': 1
}
```

### Tipos de Motivos para Ignorar
1. **"Nota já existe no banco"** - Nota com mesmo número já existe na empresa
2. **"Duplicata no XML"** - Nota duplicada dentro do mesmo arquivo XML
3. **"Erro na importação"** - Erro durante o processamento da nota
4. **"Erro ao salvar"** - Erro durante o salvamento no banco

## Interface do Usuário

### Relatório Visual
- Cards coloridos mostrando estatísticas
- Tabelas separadas para notas importadas e ignoradas
- Cores diferentes para sucesso (verde) e avisos (amarelo)

### Mensagens
- **Sucesso**: "2 NFSe importadas com sucesso!"
- **Aviso**: "1 NFSe ignorada: Nota já existe no banco"
- **Misto**: "2 NFSe importadas com sucesso! (1 ignorada)"

## Arquivos Modificados

### 1. `utils.py`
- `import_lote_nfse()`: Verifica duplicatas antes de salvar
- `import_nfse_from_xml()`: Retorna relatório detalhado
- Tratamento de erros melhorado

### 2. `views.py`
- `XMLImportView.form_valid()`: Processa relatório e mostra mensagens
- `import_xml_ajax()`: Suporte AJAX com relatório
- `get_context_data()`: Passa relatório para template

### 3. `xml_import.html`
- Seção de relatório visual
- Tabelas para notas importadas e ignoradas
- Cards com estatísticas

## Como Testar

### 1. Script de Teste
Execute o script `test_import_duplicates.py`:
```bash
cd SaudeFinanceira
python notasfiscais/test_import_duplicates.py
```

### 2. Teste Manual
1. Importe um XML com notas fiscais
2. Importe o mesmo XML novamente
3. Verifique se as duplicatas são ignoradas
4. Confirme que o relatório mostra as informações corretas

## Benefícios

1. **Sem Mais Erros**: Não há mais erros de duplicação de chave única
2. **Transparência**: Usuário sabe exatamente o que aconteceu
3. **Flexibilidade**: Pode importar XMLs múltiplas vezes sem problemas
4. **Relatório Detalhado**: Informações completas sobre o processo
5. **Interface Amigável**: Visual claro e intuitivo

## Compatibilidade

- ✅ Mantém compatibilidade com importações existentes
- ✅ Funciona com NFSe individual e lote
- ✅ Suporte a AJAX mantido
- ✅ Não quebra funcionalidades existentes

## Próximos Passos

1. Testar em ambiente de produção
2. Coletar feedback dos usuários
3. Considerar adicionar opção para sobrescrever notas existentes
4. Implementar log detalhado das importações



