"""Diagnóstico e testes do armazenamento de anexos (MEDIA_ROOT / Render Disk)."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings

from faturamento_medico.models import DocumentoAnexado


@dataclass
class MediaStorageStatus:
    media_root: str
    exists: bool
    writable: bool
    on_render: bool
    disk_mount_hint: str
    write_error: str = ''
    test_marker_path: str = ''
    total_anexos: int = 0
    anexos_ok: int = 0
    anexos_faltando: int = 0
    faltando: list[dict] = field(default_factory=list)


def _on_render() -> bool:
    return (
        os.environ.get('RENDER', '').strip().lower() in ('1', 'true', 'yes')
        or bool(os.environ.get('RENDER_EXTERNAL_HOSTNAME', '').strip())
    )


def verificar_media_gravavel(media_path: Path) -> tuple[bool, str]:
    """Tenta criar pasta, gravar e ler arquivo de teste."""
    try:
        media_path.mkdir(parents=True, exist_ok=True)
        marker = media_path / f'.healthcheck_{uuid.uuid4().hex[:8]}'
        marker.write_text('ok', encoding='utf-8')
        if marker.read_text(encoding='utf-8') != 'ok':
            return False, 'Leitura após gravação falhou.'
        marker.unlink(missing_ok=True)
        return True, ''
    except OSError as exc:
        return False, str(exc)


def diagnosticar_media_storage(
    *,
    empresa_id: int | None = None,
    limite_faltando: int = 100,
) -> MediaStorageStatus:
    media_path = Path(settings.MEDIA_ROOT)
    writable, write_error = verificar_media_gravavel(media_path)
    exists = media_path.is_dir()

    qs = DocumentoAnexado.objects.select_related('faturamento')
    if empresa_id:
        qs = qs.filter(faturamento__empresa_id=empresa_id)

    faltando: list[dict] = []
    ok = 0
    for doc in qs.iterator():
        arquivo_ok = False
        try:
            if doc.arquivo and doc.arquivo.storage.exists(doc.arquivo.name):
                arquivo_ok = True
        except OSError:
            arquivo_ok = False
        if arquivo_ok:
            ok += 1
        elif len(faltando) < limite_faltando:
            faltando.append({
                'documento_id': doc.pk,
                'faturamento_id': doc.faturamento_id,
                'nome': (doc.nome or '').strip() or (doc.arquivo.name if doc.arquivo else ''),
                'arquivo': doc.arquivo.name if doc.arquivo else '',
            })

    total = qs.count()
    if str(media_path).startswith('/var/data'):
        mount_hint = 'Render Disk em /var/data (produção)'
    elif _on_render():
        mount_hint = 'Render sem /var/data — configure disco persistente no Dashboard'
    else:
        mount_hint = 'Desenvolvimento local (pasta media/ do projeto)'

    return MediaStorageStatus(
        media_root=str(media_path),
        exists=exists,
        writable=writable,
        on_render=_on_render(),
        disk_mount_hint=mount_hint,
        write_error=write_error,
        test_marker_path=str(media_path / '.render_media_test'),
        total_anexos=total,
        anexos_ok=ok,
        anexos_faltando=total - ok,
        faltando=faltando,
    )


def gravar_marcador_teste_persistencia() -> tuple[bool, str, str]:
    """
    Grava arquivo de teste em MEDIA_ROOT para validar persistência após redeploy.
    Retorna (sucesso, caminho, conteúdo).
    """
    media_path = Path(settings.MEDIA_ROOT)
    writable, err = verificar_media_gravavel(media_path)
    if not writable:
        return False, '', err or 'MEDIA_ROOT não gravável.'

    marker = media_path / '.render_media_test'
    conteudo = f'persistencia_ok uuid={uuid.uuid4().hex}'
    try:
        marker.write_text(conteudo, encoding='utf-8')
    except OSError as exc:
        return False, '', str(exc)
    return True, str(marker), conteudo


def ler_marcador_teste_persistencia() -> tuple[bool, str]:
    """Lê marcador de teste; retorna (existe, conteúdo ou erro)."""
    marker = Path(settings.MEDIA_ROOT) / '.render_media_test'
    if not marker.is_file():
        return False, 'Marcador não encontrado — rode --gravar-teste antes do redeploy.'
    try:
        return True, marker.read_text(encoding='utf-8')
    except OSError as exc:
        return False, str(exc)
