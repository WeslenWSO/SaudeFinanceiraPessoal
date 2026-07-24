# Funcionalidade de Seleção de Empresa

## Visão Geral

Este sistema implementa uma funcionalidade completa para seleção e gerenciamento de empresas, permitindo que usuários escolham qual empresa estão trabalhando no momento.

## Funcionalidades Implementadas

### 1. Seleção de Empresa
- **Interface Visual**: Cards visuais para cada empresa disponível
- **Seleção Rápida**: Botões de seleção direta na lista
- **Validação**: Apenas empresas ativas podem ser selecionadas
- **Feedback Visual**: Indicadores claros de empresa selecionada

### 2. Navegação Intuitiva
- **Dropdown de Empresa**: Seletor na barra de navegação
- **Status Visual**: Cores diferentes para empresa selecionada vs. não selecionada
- **Acesso Rápido**: Links diretos para trocar empresa

### 3. Gerenciamento de Sessão
- **Persistência**: Empresa selecionada fica salva na sessão
- **Middleware**: Verificação automática de empresa selecionada
- **Redirecionamento**: Usuários sem empresa são direcionados para seleção

### 4. Interface Responsiva
- **Cards Adaptativos**: Layout responsivo para diferentes tamanhos de tela
- **Animações**: Efeitos hover e transições suaves
- **Bootstrap 5**: Interface moderna e consistente

## Como Usar

### Para Usuários

1. **Acessar o Sistema**
   - Faça login no sistema
   - Se não houver empresa selecionada, você será redirecionado para a seleção

2. **Selecionar Empresa**
   - Na página de seleção, clique em "Selecionar Empresa" na empresa desejada
   - A empresa será selecionada e você será redirecionado para o dashboard

3. **Trocar Empresa**
   - Use o dropdown na barra de navegação
   - Clique em "Trocar Empresa" para remover a atual
   - Selecione uma nova empresa

### Para Administradores

1. **Criar Empresas**
   - Acesse `/empresa/nova/`
   - Preencha os dados da empresa
   - A empresa será automaticamente vinculada ao usuário criador

2. **Gerenciar Empresas**
   - Acesse `/empresa/lista/`
   - Visualize, edite ou altere o status das empresas
   - Gerencie o acesso dos usuários

## Estrutura Técnica

### Models
- `Empresa`: Dados da empresa (razão social, CNPJ, status, etc.)
- `UsuarioEmpresa`: Relacionamento entre usuário e empresa

### Views
- `lista_empresas`: Lista empresas com template adaptativo
- `selecionar_empresa`: Seleção tradicional via GET
- `selecionar_empresa_ajax`: Seleção via AJAX
- `trocar_empresa`: Remove empresa da sessão

### Templates
- `selecao_rapida.html`: Interface de seleção com cards
- `Emp_List.html`: Lista tradicional de empresas
- `_nav.html`: Navegação com seletor de empresa
- `_empresa_selector_modal.html`: Modal para seleção rápida

### URLs
```
/empresa/lista/              # Lista empresas
/empresa/selecionar/<id>/     # Seleciona empresa
/empresa/selecionar-ajax/     # Seleção via AJAX
/empresa/trocar/              # Troca empresa
/empresa/atual/               # Info da empresa atual
```

## Comandos de Gerenciamento

### Criar Empresas de Teste
```bash
python manage.py criar_empresa_teste --usuario admin
```

Este comando cria 3 empresas de exemplo e as vincula ao usuário especificado.

## Middleware

O `EmpresaMiddleware` verifica automaticamente se o usuário tem uma empresa selecionada e redireciona para a seleção se necessário.

## Segurança

- Apenas usuários autenticados podem selecionar empresas
- Usuários só podem acessar empresas às quais têm permissão
- Validação de status da empresa (ativa/inativa)
- Proteção CSRF em todas as operações

## Personalização

### Cores e Estilos
Os estilos podem ser personalizados editando o CSS nos templates:
- Cores dos badges de status
- Efeitos hover dos cards
- Cores dos botões de ação

### Comportamento
- Tempo de redirecionamento após seleção
- Mensagens de feedback
- Validações adicionais

## Troubleshooting

### Problema: "Nenhuma empresa selecionada"
**Solução**: Acesse `/empresa/lista/` e selecione uma empresa

### Problema: Empresa não aparece na lista
**Solução**: Verifique se:
- A empresa está ativa
- Você tem permissão de acesso
- A empresa foi criada corretamente

### Problema: Erro ao selecionar empresa
**Solução**: 
- Verifique se está logado
- Recarregue a página
- Verifique o console do navegador para erros JavaScript

## Contribuição

Para contribuir com melhorias:
1. Teste as funcionalidades existentes
2. Documente mudanças propostas
3. Mantenha a consistência com o design atual
4. Teste em diferentes navegadores e dispositivos










