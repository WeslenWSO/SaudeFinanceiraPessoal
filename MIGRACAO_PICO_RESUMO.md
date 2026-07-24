# Migração Bootstrap → Pico.css – Resumo

## Arquivos modificados

| Arquivo | Alteração |
|---------|-----------|
| `templates/base.html` | Removidos django_bootstrap5, Bootstrap CSS/JS, SB Admin 2. Adicionado `<main class="container">`. Pico carregado via `_head.html`. Sidebar incluído por padrão. |
| `templates/parcial/_head.html` | Removidos Bootstrap, Bootstrap Icons, SB Admin 2. Adicionado Pico.css (CDN), Font Awesome, `static/css/app.css`. |
| `templates/parcial/_nav.html` | Navbar Bootstrap substituída por `<header class="app-nav">` com `<nav>`, `<ul>`, `<details role="list">` para menus (sem JS collapse). |
| `templates/parcial/_MenuSideNav.html` | Sidebar Bootstrap substituída por `<aside>` com `<nav>` e lista de links (sem collapse). |
| `templates/parcial/_footer.html` | Classes Bootstrap removidas; footer semântico com `class="container"`. |
| `templates/parcial/_empresa_selector_modal.html` | Modal Bootstrap substituído por `<dialog>`; script adaptado (sem bootstrap.Modal/Toast). |
| `templates/parcial/_dashbord.html` | Cards/rows/cols/table Bootstrap substituídos por `<article>`, `<div class="grid">`, `<table>` e `.table-wrapper`. |
| `templates/parcial/_messages.html` | `alert` substituído por `<article role="alert">`. |
| `templates/parcial/_404.html` | Página standalone com Pico; removido Bootstrap. |
| `templates/parcial/_401.html` | Página standalone com Pico; removido Bootstrap. |
| `templates/parcial/_500.html` | Fragmento com Pico; removido script Bootstrap. |
| `categoria/templates/cat-List.html` | Removidos Bootstrap do head, `btn-*`, `card`, `form-control`, `table-*`, `pagination`. Uso de `role="button"`, `<table>`, `<article>`, nav de paginação simples. |
| `dashboard/templates/relatorio_mensal.html` | Corrigido `block nav` → `block nav_`; classes Bootstrap substituídas por `<article>`, `.table-wrapper`, `<table>`. |
| `static/css/app.css` | **Novo.** Ajustes de layout (sidebar, nav topo, tabelas responsivas, botões de ação). |

## Arquivos removidos (recomendado)

Podem ser removidos ou deixados sem uso (não estão mais referenciados no base/head):

- `static/css/bootstrap.min.css`
- `static/js/bootstrap.bundle.min.js`

Não apagar pastas de outros projetos (venv, etc.). Se existir `static/css/style.css` ou `static/css/main.css` que importem Bootstrap, remover apenas as importações ou referências ao Bootstrap.

## Pontos para revisão manual

1. **Modal de empresa**  
   O modal de seleção de empresa agora é um `<dialog>`. Qualquer botão que abria o modal Bootstrap deve usar `data-open-empresa-modal` para o script atual abrir o dialog. Verifique onde o modal era aberto (ex.: menu “Trocar empresa”) e adicione esse atributo se necessário.

2. **Templates que ainda usam classes Bootstrap**  
   Substituir gradualmente em:
   - `usuario/templates/usuarioList.html`, `usuario-add-alterar.html`
   - `templates/servicos_medicos/*.html` (tabela_list, tabela_form, servicos_list, servicos_form, convenio_*, cabecalho_*)
   - `templates/relatoriorecebiveis/*.html` (list, form, detail, delete, import_csv, import_csv_preview)
   - `dashboard/templates/relatorio_mensal.html` já foi ajustado (block nav_ e tabela Pico).
   - Demais listagens/formulários em: extrato, notasfiscais, notafiscalentrada, contasapagar, contasareceber, faturamento_medico, etc.

   Padrão sugerido:
   - Botões: `<a href="..." role="button">` (primário) ou `role="button" class="secondary"` / `class="contrast"`.
   - Formulários: `<label>`, `<input>`, `<select>`, `<textarea>` sem `form-control`; Pico estiliza por padrão.
   - Tabelas: `<table>` dentro de `<div class="table-wrapper">` para scroll horizontal.
   - Cards: `<article>`.

3. **django_bootstrap5**  
   Não é mais usado no base. Se algum template usar `{% load django_bootstrap5 %}` ou `{% bootstrap_form form %}`, ou trocar para renderização manual (ex.: `{{ form.as_p }}`) ou criar um template de form compatível com Pico e remover o app de `INSTALLED_APPS` quando não houver mais uso.

4. **Página de login**  
   `accounts/templates/accounts/login.html` não estende o base atual e usa estilos próprios (`.form-control`, `.btn-login`, etc.). Pode permanecer assim ou ser adaptada para Pico (ex.: estender base e usar `<main class="container">` e componentes Pico).

5. **Cópia do menu**  
   `templates/parcial/_MenuSideNav copy.html` ainda usa Bootstrap; pode ser removida ou atualizada se for usada em algum lugar.

## Uso do Pico

- **Botões:** `<button type="submit">Salvar</button>`, `<a href="..." role="button">Editar</a>`, `role="button" class="secondary"` para secundário, `class="contrast"` para destaque negativo.
- **Formulários:** `<form>`, `<label for="id">`, `<input id="id">`, `<select>`, `<textarea>`; Pico aplica o estilo.
- **Tabelas:** `<table>` com `<thead>` e `<tbody>`; para mobile, envolver em `<div class="table-wrapper">`.
- **Agrupamentos:** `<article>` para blocos tipo card; `<div class="grid">` para colunas responsivas.
- **Avisos:** `<article role="alert">` ou `<mark>`.
- **Menus expansíveis:** `<details>` e `<summary>` (já usado na nav).

## CDN do Pico

No `_head.html` está:

```html
<link rel="stylesheet" href="https://unpkg.com/@picocss/pico@2/css/pico.min.css">
```

Para fixar versão, use por exemplo `@2.0.6` em vez de `@2`.
