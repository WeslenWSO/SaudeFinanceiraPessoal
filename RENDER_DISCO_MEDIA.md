# Ativar disco persistente de anexos no Render (PDFs / media)

Servico: https://dashboard.render.com/web/srv-d9hui8jtqb8s73a97d70

O `render.yaml` ja declara:

- Disco `media-uploads`, 10 GB, montado em `/var/data`
- `MEDIA_ROOT=/var/data/media`
- `RENDER=true`

## Opcao A — Sync Blueprint (recomendado)

1. Render Dashboard -> **Blueprints** -> repositorio **SaudeFinanceiraPessoal**
2. **Sync** (ou Manual Deploy do web service apos push em `main`)
3. Aba **Disks** do servico **saude-financeira** / **FinancasPessoais**:
   - mount path: `/var/data`
   - tamanho: 10 GB

## Opcao B — Disco manual

1. **FinancasPessoais** -> **Disks** -> **Add Disk**
2. Mount path: `/var/data` | Size: 10 GB
3. **Environment** -> `MEDIA_ROOT` = `/var/data/media`
4. **Manual Deploy**

## Validar nos logs

Apos deploy, em **Logs**:

```
[startup] MEDIA_ROOT=/var/data/media exists=True writable=True
[startup] anexos total=N ok=X faltando=Y
```

Shell (opcional):

```bash
python manage.py verificar_anexos_media
python manage.py verificar_anexos_media --gravar-teste
# redeploy
python manage.py verificar_anexos_media --ler-teste
```

## Anexos antigos perdidos

Registros no Postgres sem arquivo fisico precisam ser **reenviados** uma vez (Detalhes -> Anexar).
Liste no Shell: `python manage.py verificar_anexos_media --somente-faltando`

## S3/R2 (futuro)

Variavel `USE_S3_STORAGE=true` + `django-storages[boto3]` + bucket AWS/R2.
Enquanto inativo, anexos usam Render Disk em `/var/data/media`.
