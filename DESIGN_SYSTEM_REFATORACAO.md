# Design System e Refatoração de Telas

## Arquivos alterados / criados

### CSS
- **`static/css/app.css`** – Design System adicionado ao final do arquivo:
  - Variáveis de compatibilidade (`--muted-border-color`, `--border-radius`, `--card-background-color`, `--primary`, etc.)
  - `.page`, `.page-head`, `.page-title`, `.page-subtitle`
  - `.panel`, `.panel-tight`
  - `.toolbar`, `.toolbar-left`, `.toolbar-right`
  - `.filters-grid`, `.col-12`, `.col-6`, `.col-4`, `.col-3` (com media para mobile)
  - `.table-wrap` e estilos de tabela
  - Família `.btn` (`.btn`, `.btn-sm`, `.btn-icon`, `.btn-primary`, `.btn-secondary`, `.btn-muted`, `.btn-danger`)
  - `.btn-group`
  - `.badge`, `.badge-success`, `.badge-warning`, `.badge-danger`, `.badge-muted`
  - `dialog article header` para modais nativos

### Partials (templates reutilizáveis)
- **`templates/parcial/_page_head.html`** – Bloco esquerdo do cabeçalho (título + subtítulo)
- **`templates/parcial/_toolbar.html`** – Estrutura toolbar-left / toolbar-right (com blocks)
- **`templates/parcial/_filters_panel.html`** – Painel de filtros com `<details>` (com block)
- **`templates/parcial/_table_wrap.html`** – Envolve tabela em `.table-wrap` (com block)

### Templates refatorados
- **`empresa/templates/empresa/Emp_List.html`** – Listagem de empresas com page-head, panel, filters-grid, table-wrap, btn-group e badges do Design System
- **`notasfiscais/templates/notasfiscais/nfse_list.html`** – Listagem de NFSe: page-head, resumo em panels, filtros em section + details, toolbar, table-wrap, empty-state, modais convertidos para `<dialog>`, botões e badges padronizados

---

## Exemplo antes/depois

### Empresas (Emp_List.html)

**Antes (trecho):**
```html
<div class="container my-2">
  <div class="row align-items-center g-2">
    <div class="col-auto">
      <a href="..." class="btn btn-primary"><i class="bi bi-plus-circle"></i> Novo</a>
    </div>
    <div class="col-md-5">
      <form method="get" class="d-flex w-100">
        <div class="input-group input-group-sm w-100">
          <input type="text" name="q" class="form-control" placeholder="Pesquisar...">
          <button type="submit" class="btn btn-primary px-2">...</button>
        </div>
      </form>
    </div>
    ...
  </div>
</div>
<table class="table table-striped table-bordered">
  ...
  <td>
    <button class="btn btn-success btn-sm me-2">...</button>
    <a href="..." class="btn btn-info btn-sm">...</a>
  </td>
</table>
```

**Depois (trecho):**
```html
<div class="page">
  <div class="page-head">
    {% include 'parcial/_page_head.html' with title="Empresas" subtitle="Gerencie as empresas vinculadas ao seu usuário." %}
    <div class="btn-group">
      <a href="{% url 'empresa:empresa_create' %}" class="btn btn-primary"><i class="fas fa-plus"></i> Novo</a>
    </div>
  </div>
  <section class="panel panel-tight">
    <form method="get" id="formFiltrosEmpresa">
      <div class="filters-grid">
        <div class="col-6"><input type="search" name="q" placeholder="Pesquisar por nome ou CNPJ..." ...></div>
        <div class="col-3"><button type="submit" class="btn btn-primary">...</button></div>
        <div class="col-3"><label>Por página</label><select name="per_page">...</select></div>
      </div>
    </form>
  </section>
  <div class="panel" style="padding: 0;">
    <div class="table-wrap">
      <table>...</table>
    </div>
  </div>
</div>
<!-- Coluna Ações -->
<td style="text-align: right;">
  <div class="btn-group">
    <button class="btn btn-primary btn-sm">...</button>
    <a href="..." class="btn btn-muted btn-sm btn-icon" title="Visualizar"><i class="fas fa-eye"></i></a>
    <a href="..." class="btn btn-muted btn-sm btn-icon" title="Editar"><i class="fas fa-pen"></i></a>
  </div>
</td>
```

### Notas Fiscais (nfse_list.html)

**Antes:** Bootstrap (container-fluid, row, col-*, card, btn btn-primary/btn-warning, form-control, form-floating, table table-striped, modal fade, pagination).

**Depois:** Design System (page, page-head, panel, filters-grid, toolbar, table-wrap, btn btn-primary/btn-muted btn-sm, badge badge-success/badge-warning, empty-state, `<dialog>` no lugar de Bootstrap modal). Filtros em `<details open>` colapsável. Botão “Aplicar Regra Imposto” abre o dialog com `document.getElementById('modalRegraImposto').showModal();`. Fechamento do modal com `.close()`.

---

## Pontos que exigem revisão manual

1. **Notas Fiscais – coluna Ações da tabela**  
   Os botões de ação (Detalhes, Editar, Excluir) ainda usam classes antigas em parte (btn-outline-*). Vale padronizar para `btn btn-muted btn-sm btn-icon` e envolver em `.btn-group` para alinhar com o restante do sistema.

2. **Notas Fiscais – badges na tabela**  
   Há uso de `badge bg-info`, `badge bg-warning`, `badge bg-secondary` em células (Sócio, Base Serviço, Iss Retido, Conciliação, etc.). Substituir por `badge badge-success`, `badge badge-warning`, `badge badge-muted` conforme o Design System.

3. **Paginação NFSe**  
   A paginação da lista de NFSe ainda usa estrutura antiga (ul.pagination, page-item, page-link). Pode ser trocada por toolbar + links com classes `.btn .btn-secondary .btn-sm`, no mesmo padrão da listagem de Empresas.

4. **Mensagens (mostrarMensagem)**  
   O JavaScript que exibe mensagens de sucesso/erro usa classes `alert alert-success`, `alert-danger`, etc., e `data-bs-dismiss`. Ajustar para usar as classes `.alert-modern` (ou equivalente) e remover dependência de Bootstrap (ex.: botão de fechar que apenas esconde o elemento).

5. **carregarDetalhes – conteúdo do modal**  
   O HTML retornado pelo AJAX pode conter classes Bootstrap (alert, table, etc.). Se a API devolver HTML, considerar estilizar no backend ou no front com as classes do Design System.

6. **Outras listagens**  
   Aplicar o mesmo padrão (page-head, panel, filters-grid, table-wrap, btn-group) nas demais telas de listagem do projeto (categoria, cliente, fornecedor, etc.) conforme o checklist do PASSO 5.

---

## Checklist de padronização (outras telas)

- [ ] Todas as listagens têm `.page-head` com título e ações à direita
- [ ] Filtros dentro de `.panel` (e opcionalmente `<details>`)
- [ ] Tabelas dentro de `.table-wrap`
- [ ] Coluna Ações com `.btn-group` e `.btn .btn-sm` / `.btn-icon`
- [ ] Remoção de estilos inline desnecessários e de classes antigas (btn btn-primary do Bootstrap, form-control, etc.)
- [ ] Formulários create/edit com `.panel` e `.toolbar` nos botões (Salvar/Cancelar)
