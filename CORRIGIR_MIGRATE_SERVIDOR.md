# Corrigir erros de migrate no servidor

Siga estes passos **no servidor** (MySQL em produção). Você pode fazer tudo **via PuTTY** (SSH).

---

## Ordem das migrations (duplicate column / 0002_initial)

O Django **não** aplica migrations na ordem do número do arquivo: ele segue o **grafo de dependências**. Por isso pode aparecer "duplicate column" ou erro ao aplicar `0002_initial`.

- **Se no servidor existir** `contasareceber/migrations/0002_initial.py`: **apague esse arquivo** (no servidor). O projeto usa só `0002_remove_contaareceber_banco_contaareceber_conta_banco_and_more.py`, que já trata `conta_banco_id` de forma segura.
- Suba a **versão atual** de `contasareceber/migrations/0002_remove_contaareceber_banco_contaareceber_conta_banco_and_more.py` (ela só adiciona `conta_banco_id` se a coluna ainda não existir).

---

## Como fazer pelo servidor (via PuTTY)

### 1. Conectar no servidor
Abra o PuTTY e conecte no servidor (IP, usuário e senha). Você ficará no terminal (bash).

### 2. Rodar o SQL no MySQL (pelo terminal)

**Se você já está no PuTTY na pasta do sistema** (ex.: `root@Wesley:/var/www/html/SaudeFinanceira#`):

1. Troque `USUARIO` e `NOME_DO_BANCO` pelos dados do MySQL do projeto (usuário e nome do banco). Se não lembrar o nome do banco, na mesma pasta rode:  
   `grep -E "NAME|USER" SaudeFinanceira/settings.py`  
   (ou abra `settings.py` e veja `DATABASES`).

2. Rode este comando **na mesma pasta** (`/var/www/html/SaudeFinanceira`):

```bash
mysql -u USUARIO -p NOME_DO_BANCO -e "DELETE FROM django_migrations WHERE app = 'contasareceber' AND name = '0009_fix_foreign_key_alter_field';"
```

O MySQL vai pedir a senha; digite e pressione Enter.

**Exemplo:** usuário `root`, banco `saude_financeira`:
```bash
mysql -u root -p saude_financeira -e "DELETE FROM django_migrations WHERE app = 'contasareceber' AND name = '0009_fix_foreign_key_alter_field';"
```

A pasta em que você está (PuTTY) não precisa ser a do projeto para o `mysql`; o comando funciona de qualquer diretório. Só o **migrate** (passo 4) precisa ser rodado de dentro da pasta do projeto.

### 3. Subir o arquivo da migration (FileZilla)
No seu PC, abra o **FileZilla** e conecte no mesmo servidor (SFTP). Envie o arquivo:

- **Do seu PC:** `contasareceber/migrations/0009_fix_foreign_key_alter_field.py`  
- **Para o servidor:** `/var/www/html/SaudeFinanceira/contasareceber/migrations/`

(substitua o arquivo antigo se já existir)

### 4. Rodar o migrate (no PuTTY)
No PuTTY, na pasta do projeto:

```bash
cd /var/www/html/SaudeFinanceira
source venv/bin/activate
python manage.py migrate
```

Pronto. Se aparecer outro erro, copie a mensagem e envie.

**Se você já subiu a migration 0009 em versão no-op** (arquivo com `operations = []`): pode **pular o passo 2** (SQL) e fazer só o **3** (FileZilla) e **4** (migrate).

---

## Passo a passo completo (alternativo)

## Passo 1: Fazer backup do banco

```bash
mysqldump -u SEU_USUARIO -p NOME_DO_BANCO > backup_antes_migrate_$(date +%Y%m%d).sql
```

## Passo 2: Conferir migrations aplicadas de contasareceber

No servidor:

```bash
cd /var/www/html/SaudeFinanceira
source venv/bin/activate
python manage.py showmigrations contasareceber
```

Anote se a **0003_baixacontaareceber** está com `[X]` (aplicada) e se a **0009_fix_foreign_key_alter_field** está com `[X]`.

## Passo 3: Ajustar o histórico no MySQL

Conecte no MySQL (phpMyAdmin, linha de comando ou DBeaver) e rode:

```sql
-- Troque NOME_DO_BANCO pelo nome real do seu banco (ex: saude_financeira)
USE NOME_DO_BANCO;

-- Remove a 0009 do histórico para o Django reaplicá-la na ordem correta
DELETE FROM django_migrations 
WHERE app = 'contasareceber' 
  AND name = '0009_fix_foreign_key_alter_field';
```

Se não tiver certeza do nome exato da migration:

```sql
SELECT id, app, name FROM django_migrations 
WHERE app = 'contasareceber' 
ORDER BY id;
```

Use o valor exato de `name` no `DELETE` se for diferente de `0009_fix_foreign_key_alter_field`.

## Passo 4: Arquivos no servidor (FileZilla)

Garanta que estes arquivos estão atualizados no servidor (substitua os que já existem):

- `contasareceber/migrations/0003_baixacontaareceber.py`
- `contasareceber/migrations/0009_fix_foreign_key_alter_field.py`
- `extrato/migrations/0003_extratomovimento.py`

## Passo 5: Rodar migrate de novo

```bash
cd /var/www/html/SaudeFinanceira
source venv/bin/activate
python manage.py migrate
```

A 0009 será aplicada de novo **depois** da 0003 e o KeyError deve sumir.

## Se ainda der erro

1. Envie a saída de:
   ```bash
   python manage.py showmigrations contasareceber
   python manage.py showmigrations extrato
   ```

2. Se a **0003_baixacontaareceber** não estiver aplicada (`[ ]`), tente:
   ```bash
   python manage.py migrate contasareceber 0003_baixacontaareceber
   ```
   Depois:
   ```bash
   python manage.py migrate
   ```
