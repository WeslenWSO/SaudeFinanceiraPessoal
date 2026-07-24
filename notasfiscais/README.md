# Sistema de Notas Fiscais de Serviço (NFSe)

## Visão Geral

Este módulo implementa um sistema completo de gestão de Notas Fiscais de Serviço (NFSe) para o sistema SaudeFinanceira, permitindo o cadastro, edição, visualização e controle de recebimentos de notas fiscais de serviço.

## Funcionalidades Principais

### 1. Cadastro de NFSe
- **Campos obrigatórios:**
  - Número da nota
  - Série
  - Data de emissão
  - CNPJ/CPF do cliente
  - Nome/Razão social do cliente
  - Valor bruto
  - Valor líquido
  - Discriminação do serviço
  - Forma de pagamento

- **Campos opcionais:**
  - Observações
  - Data de cancelamento
  - Autorização de cancelamento
  - Data do recebimento
  - Banco
  - Valor recebido
  - Status
  - Status de conciliação

### 2. Importação de XML
- Suporte a múltiplos padrões de XML:
  - ABRASF
  - GINFES
  - São Paulo
  - Padrões genéricos
- Validação automática de arquivos
- Preview dos dados extraídos
- Drag & drop para upload

### 3. Gestão de Recebimentos
- Registro de recebimentos parciais ou totais
- Atualização automática de status
- Controle de conciliação bancária
- Histórico de recebimentos

### 4. Controle de Status
- **Status da NFSe:**
  - Pendente
  - Pago
  - Cancelado
  - Vencido

- **Status de Conciliação:**
  - Não Conciliado
  - Parcialmente Conciliado
  - Conciliado

### 5. Relatórios e Filtros
- Listagem com paginação
- Filtros por:
  - Número da nota
  - Cliente
  - CNPJ/CPF
  - Status
  - Período de emissão
- Estatísticas em tempo real
- Busca textual

## Estrutura do Sistema

### Models
- `NotaFiscalServico`: Modelo principal com todos os campos necessários

### Views
- `NFSeListView`: Lista todas as NFSe com filtros e estatísticas
- `NFSeCreateView`: Criação de nova NFSe
- `NFSeUpdateView`: Edição de NFSe existente
- `NFSeDetailView`: Visualização detalhada
- `NFSeDeleteView`: Confirmação de exclusão
- `NFSeRecebimentoView`: Registro de recebimentos
- `XMLImportView`: Importação de XML
- `import_xml_ajax`: API para importação AJAX

### Forms
- `XMLUploadForm`: Upload e validação de XML
- `NFSeForm`: Formulário de criação
- `NFSeUpdateForm`: Formulário de edição
- `NFSeRecebimentoForm`: Formulário de recebimento

### Utils
- `XMLNFSeProcessor`: Processador de XML com suporte a múltiplos padrões
- Funções de importação e processamento

## URLs

- `/nfse/` - Lista de NFSe
- `/nfse/create/` - Criar nova NFSe
- `/nfse/import/` - Importar XML
- `/nfse/<id>/` - Detalhes da NFSe
- `/nfse/<id>/update/` - Editar NFSe
- `/nfse/<id>/delete/` - Excluir NFSe
- `/nfse/<id>/recebimento/` - Registrar recebimento

## Como Usar

### 1. Criar NFSe Manualmente
1. Acesse `/nfse/create/`
2. Preencha os campos obrigatórios
3. Clique em "Salvar NFSe"

### 2. Importar NFSe do XML
1. Acesse `/nfse/import/`
2. Arraste e solte o arquivo XML ou clique para selecionar
3. Visualize o preview dos dados extraídos
4. Clique em "Importar XML"

### 3. Registrar Recebimento
1. Acesse os detalhes da NFSe
2. Clique em "Registrar Recebimento"
3. Preencha a data e valor recebido
4. O status será atualizado automaticamente

### 4. Gerenciar NFSe
- Use os filtros para encontrar NFSe específicas
- Visualize estatísticas em tempo real
- Edite informações conforme necessário
- Controle o ciclo de vida completo da NFSe

## Suporte a XML

O sistema suporta múltiplos padrões de XML de NFSe:

### ABRASF
- Namespace: `http://www.abrasf.org.br/ABRASF/arquivos/nfse.xsd`
- Elementos principais: `InfNfse`, `Tomador`, `Servico`

### GINFES
- Namespace: `http://www.ginfes.com.br/servicos/consultarLoteRps/v03`
- Elementos principais: `CompNfse`, `Tomador`, `Servico`

### São Paulo
- Namespace: `http://www.prefeitura.sp.gov.br/nfe`
- Elementos principais: `Nfse`, `Tomador`, `Servico`

### Padrão Genérico
- Busca por elementos comuns em diferentes padrões
- Fallback para casos não cobertos pelos padrões específicos

## Validações

- Arquivo XML válido e bem formado
- Tamanho máximo de 5MB
- Codificação UTF-8
- Verificação de duplicidade por número da nota
- Validação de campos obrigatórios
- Formatação de datas e valores

## Personalização

O sistema é altamente personalizável:

- Templates responsivos com Bootstrap 5
- Estilos CSS customizáveis
- JavaScript para interatividade
- Formulários com validação em tempo real
- Mensagens de feedback personalizadas

## Dependências

- Django 4.2+
- Python 3.8+
- Bootstrap 5
- FontAwesome (para ícones)

## Contribuição

Para contribuir com o desenvolvimento:

1. Mantenha a estrutura de código existente
2. Adicione testes para novas funcionalidades
3. Documente alterações importantes
4. Siga os padrões de nomenclatura do projeto

## Suporte

Para suporte técnico ou dúvidas sobre o sistema, consulte a documentação do Django ou entre em contato com a equipe de desenvolvimento.




