from __future__ import annotations

from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_date

from empresa.models import Empresa
from empresa.nfse_nacional_config import portal_nacional_site_credenciais_para_empresa
from notasfiscais.nfse_xml_copia import (
    PastaNfseInacessivelError,
    pasta_inbox_downloads_portal_nacional,
    validar_periodo_um_mes_portal_nacional,
)
from notasfiscais.portal_emitidas_selenium import run_emitidas_selenium
from notasfiscais.portal_extensao_service import (
    coletar_xml_pdf_de_diretorio,
    organizar_arquivos_cancelados_na_inbox_portal,
    processar_portal_extensao_arquivos,
)


class Command(BaseCommand):
    help = (
        "Automação do Portal Nacional (Selenium + Chrome ou Edge) ou importação de XML/PDF já baixados de uma pasta. "
        "Após o download, importa automaticamente os XML do período na pasta do mês e também os de subpasta "
        "Cancelada/ (sempre como nota cancelada, valores zerados). "
        "Credenciais: cadastro da empresa (login/senha do site). "
        "Requer: pip install selenium e navegador Chrome ou Edge instalado; com --perfil: pasta user-data-dir dedicada (extensões)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--empresa-id", type=int, required=True, help="ID da empresa (sessão de cadastro).")
        parser.add_argument("--inicio", type=str, required=True, help="Data inicial YYYY-MM-DD.")
        parser.add_argument("--fim", type=str, required=True, help="Data final YYYY-MM-DD.")
        parser.add_argument(
            "--modo",
            type=str,
            choices=("emitidas", "pasta"),
            default="emitidas",
            help="emitidas: abre o navegador e tenta login/período/download. pasta: só importa arquivos de --pasta.",
        )
        parser.add_argument(
            "--pasta",
            type=str,
            default="",
            help="Com --modo pasta: diretório com .xml e .pdf baixados (ex.: pasta da extensão).",
        )
        parser.add_argument(
            "--usuario",
            type=str,
            default="",
            help="Username Django para import_nfse_from_xml (padrão: primeiro superusuário).",
        )
        parser.add_argument(
            "--headless",
            action="store_true",
            help="Navegador sem janela (pode falhar com Gov.br/captcha).",
        )
        parser.add_argument(
            "--pausa",
            action="store_true",
            help="Com navegador visível: antes de fechar, aguarda Enter no terminal para você concluir downloads manualmente.",
        )
        parser.add_argument(
            "--perfil",
            action="store_true",
            help="Força Chrome/Edge com perfil em disco (extensões); use a mesma pasta em NFSE_PORTAL_PLAYWRIGHT ou a predefinida.",
        )
        parser.add_argument(
            "--sem-perfil",
            dest="sem_perfil",
            action="store_true",
            help="Força perfil temporário (sem pasta fixa de extensões).",
        )

    def handle(self, *args, **options):
        eid = options["empresa_id"]
        di = parse_date((options["inicio"] or "").strip())
        df = parse_date((options["fim"] or "").strip())
        if not di or not df:
            raise CommandError("--inicio e --fim devem ser datas válidas (YYYY-MM-DD).")
        if di > df:
            raise CommandError("Data inicial maior que a final.")

        empresa = Empresa.objects.filter(pk=eid).first()
        if not empresa:
            raise CommandError(f"Empresa id={eid} não encontrada.")

        User = get_user_model()
        uname = (options.get("usuario") or "").strip()
        if uname:
            user = User.objects.filter(username=uname).first()
            if not user:
                raise CommandError(f"Usuário Django «{uname}» não encontrado.")
        else:
            user = User.objects.filter(is_superuser=True).order_by("id").first()
            if not user:
                user = User.objects.order_by("id").first()
            if not user:
                raise CommandError("Nenhum usuário Django encontrado. Informe --usuario.")

        cred = portal_nacional_site_credenciais_para_empresa(empresa)
        login = (cred.get("login") or "").strip()
        senha = (cred.get("senha") or "").strip()
        modo = (options.get("modo") or "emitidas").strip()
        if options.get("perfil") and options.get("sem_perfil"):
            raise CommandError("Use apenas um de --perfil ou --sem-perfil.")
        perfil_kw: bool | None = None
        if options.get("sem_perfil"):
            perfil_kw = False
        elif options.get("perfil"):
            perfil_kw = True

        work_dir: Path
        if modo == "pasta":
            pasta = (options.get("pasta") or "").strip()
            if not pasta:
                raise CommandError("--modo pasta exige --pasta=C:\\caminho\\da\\pasta")
            work_dir = Path(pasta)
            if not work_dir.is_dir():
                raise CommandError(f"Pasta não encontrada: {work_dir}")
        else:
            try:
                validar_periodo_um_mes_portal_nacional(di, df)
            except ValueError as e:
                raise CommandError(str(e)) from e
            if not login or not senha:
                raise CommandError(
                    "Cadastre login e senha do Portal nacional em Configuração de integração da empresa antes de usar --modo emitidas."
                )
            self.stdout.write(self.style.NOTICE("Iniciando Selenium (Chrome ou Edge)…"))
            try:
                dl_inbox = pasta_inbox_downloads_portal_nacional(empresa, di, df)
            except ValueError as e:
                raise CommandError(str(e)) from e
            except PastaNfseInacessivelError as e:
                raise CommandError(str(e)) from e
            if dl_inbox:
                self.stdout.write(self.style.NOTICE(f"Downloads do navegador em: {dl_inbox}"))
            try:
                work_dir = run_emitidas_selenium(
                    login,
                    senha,
                    di,
                    df,
                    headless=bool(options.get("headless")),
                    pausa_interativa=bool(options.get("pausa")) and not bool(options.get("headless")),
                    log=lambda m: self.stdout.write(m),
                    perfil_persistente=perfil_kw,
                    download_dir=dl_inbox,
                )
            except Exception as e:
                raise CommandError(str(e)) from e

        n_org = organizar_arquivos_cancelados_na_inbox_portal(
            work_dir, on_log=lambda m: self.stdout.write(m)
        )
        if n_org:
            self.stdout.write(
                self.style.NOTICE(
                    f"Organização na inbox: {n_org} ficheiro(s) movido(s) para {work_dir / 'Cancelada'}."
                )
            )

        itens = coletar_xml_pdf_de_diretorio(work_dir)
        if not itens:
            raise CommandError(
                f"Nenhum .xml encontrado em {work_dir} (nem em {work_dir / 'Cancelada'}). "
                "Com --modo emitidas, use a pausa ou verifique o screenshot na pasta do mês; "
                "com --modo pasta, aponte para a pasta onde a extensão gravou os ficheiros."
            )
        n_ca = sum(1 for it in itens if len(it) == 4 and it[3])
        if n_ca:
            self.stdout.write(
                self.style.NOTICE(
                    f"{n_ca} XML(s) na subpasta Cancelada/ serão importados como notas canceladas (valores zerados)."
                )
            )

        def _warn(msg: str) -> None:
            self.stdout.write(self.style.WARNING(msg))

        res = processar_portal_extensao_arquivos(
            empresa,
            user,
            di,
            df,
            itens,
            False,
            on_warning=_warn,
            pasta_manifest=work_dir,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Concluído: importadas={res['total_importadas']}, ignoradas={res['total_ignoradas']}, "
                f"erros={res['total_erros']}, fora_período={res['erros_periodo_count']}"
            )
        )
