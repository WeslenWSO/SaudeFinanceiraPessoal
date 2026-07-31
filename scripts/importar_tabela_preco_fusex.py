#!/usr/bin/env python
"""
Importa tabela de preços FUSEX (Medicinarte) vinculada aos ServicosMedicos.

  set DATABASE_URL=postgresql://...
  python scripts/importar_tabela_preco_fusex.py
  python scripts/importar_tabela_preco_fusex.py --dry-run
  python scripts/importar_tabela_preco_fusex.py --empresa-id 16
"""
from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")

from importar_servicos_medicos_lista import _codigos_unicos  # noqa: E402

CONVENIO_NOME = "FUSEX"
CABECALHO_NOME = "TABELA - FUSEX"
CABECALHO_NOME_LEGADO = "TABELA FUSEX"
EMPRESA_ID_DEFAULT = 16

# (código bruto, descrição, valor R$) — mesma ordem/regras de códigos da importação de serviços
TABELA_RAW: list[tuple[str, str, str]] = [
    ("41301323", "Tonometria", "49,22"),
    ("40103137", "Campimetria", "136,08"),
    ("41301080", "Cerastoscopia/Topografia Corneá", "186,18"),
    ("41301129", "Curva Tensional Diária", "122,45"),
    ("41301242", "Gonioscopia", "47,05"),
    ("41301250", "Mapeamento de Retina", "86,14"),
    ("41301269", "Microscopia Especular", "216,68"),
    ("41301307", "PAM/Potencial de Acuidade Visual", "47,46"),
    ("41301315", "Retinografia", "89,42"),
    ("41501012", "Biometria ultrassônica-Ecobiometria", "154,45"),
    ("41501128", "Paquimetria", "90,02"),
    ("40901017", "USG Globo Ocular", "185,38"),
    ("41501144", "Tomografia de Coerência Óptica", "382,5"),
    ("30306019", "Capsulotomia", "700"),
    ("30306027", "Facectomia com implante de lente monofocal", "4500"),
    ("30303010", "Transplante de Membrana Aminiótica", "2000"),
    ("30303109", "Exerese de Tumor de Conjuntiva", "1900"),
    ("30303010", "Pterígio + Transplante de Membrana", "2500"),
    ("30301190", "Ressecção de Tumor Palpebral", "1900"),
    ("30304105", "Cirurgia Refrativa Convencional", "1900"),
    ("40201120", "Endoscopia Digestiva Alta sem Biópsia", "627,72"),
    ("40202615", "Endoscopia digestiva alta com biópsia e teste de urease", "751,61"),
    ("40202038", "Endoscopia digestiva alta com biópsia e/ou citologia", "732,09"),
    ("40201082", "Colonoscopia (Retossigmoidoscopia)", "938,67"),
    ("40202666", "Colonoscopia com biópsia e citopatologia", "984,81"),
    ("40202712", "Colonoscopia com mucosectomia", "1472,35"),
    ("30911079", "Cateterismo Cardíaco", "4534,16"),
    ("30912105", "Angioplastia Coronária com 1 stent convencional", "11775"),
    ("30912105", "Angioplastia Coronária com 2 stent convencional", "16675"),
    ("30912105", "Angioplastia Coronária com 1 stent farmacologia", "21566,99"),
    ("30912105", "Angioplastia Coronária com 2 stent farmacologia", "31766,99"),
    ("-", "STENT CONVENCIONAL ADICIONAL", "4000"),
    ("-", "STENT FARMACOLÓGICO ADICIONAL", "8500"),
    ("40201198", "Vídeo endoscopia do esfincter velo-palatino com ótica flexível", "250"),
    ("40201210", "Video- endoscopia naso- sinusal com ótica flexivel", "290"),
    ("40201252", "Video- faringo laringoscopia com endoscópio flexivel", "350"),
    ("40201260", "Video- faringo laringoscopia com endoscópio flexível", "290"),
    ("4021236", "Vídeo- laringo estroboscopia com endoscópio flexivel", "350"),
    ("40201244", "Videolaringo estroboscopia com endoscópio flexível", "325"),
    ("20104065", "Cerumen- remoção- unilateral", "50"),
    ("30501083", "Corpo estranhos retirada em consultório (nariz)", "150"),
    ("40103013", "Análise computadorizada de voz", "150"),
    ("40103021", "Análise computadorizada de papila e/ou fibras nervosas monocular", "180"),
    ("40103030", "Análise computadorizada do segmento anterior monocular", "220"),
    ("40103064", "Audiometria de tronco cerebral (PEA) BERA", "500"),
    ("40103064", "Audiometria de tronco cerebral (PEA) BERA EM CENTRO CIRÚRGICO", "800"),
    ("40103510", "Polissonografia", "510"),
    ("40103072", "Audiometria Tonal", "80"),
    ("40103080", "Audiometria Tonal limiar infantil condicionada", "200"),
    ("40103099", "Audiometria vocal pesquisa de limiar de discriminação", "60"),
    ("40103102", "Audiometria vocal pesquisa de limiar de inteligibilidade", "60"),
    ("40103420", "Imitanciometria de alta frequência", "100"),
    ("40103439", "Impedanciometria timpanometria", "100"),
    ("40103455", "Otoemissões acústicas produtos de distorção", "130"),
    ("40103749", "Vectoeletronistagmografia computadorizada", "220"),
    ("31101577", "Nefrolitotripsia percutânea unilateral a laser", "12500"),
    ("31102050", "Colocação distópica de duplo J unilateral", "2500"),
    ("31102360", "Ureterorrenolitotripsia flexível a laser unilateral colocação de Duplo J", "12500"),
    ("31102565", "Ureterorrenal Litotripsia rigida unilateral a laser", "10150"),
    ("31103472", "Retirada endoscópica de duplo J", "1300"),
    ("31103472", "Ressecção endoscópica da próstata", "6000"),
    ("31103456", "Tumor vesical ressecção endoscópica", "3500"),
    ("31103359", "Incontinência urinária -tratamento cirúrgico suprapúbico", "2712,65"),
    ("31103561", "Cistolitotripsia a laser", "8000"),
    ("31104223", "Uretrotomia interna", "2500"),
    ("40201066", "Cistoscopia e/ou uretroscopia", "1600"),
    ("31203043", "Hidrocele unilateral- correção cirúrgica", "1400"),
    ("31203043", "Hidrocele bilateral- correção cirúrgica", "2000"),
    ("31023078", "Orquiectomia unilateral", "4500"),
    ("31203108", "Torção de testiculo- cura cirúrgica", "5000"),
    ("31203124", "Varicocele unilateral- correção cirúrgica", "2500"),
    ("31206220", "Postectomia", "2000"),
    ("31205046", "Vasectomia bilateral", "3500"),
    ("41001230", "Tomografia computadorizada diagnóstica-Angiotomografia coronariana", "2800"),
    ("40103234", "SISTEMA NERVOSO EEGQ quantitativo (mapeamento Cerebral)", "500"),
    ("20104189", "Sessão de Oxigenoterapia Hiperbarica", "650"),
    ("31602274", "Anestesia para exames de Tomografia Computadorizada", "1220,38"),
    ("31602282", "Anestesia para exames de Ressonância Magnética", "1220,38"),
    ("2.01.03.30.1", "Reposição Viscoelástica para articulação no joelho com Synvisc One 6ml", "2200"),
    ("2.01.03.30.1", "Reposição Viscoelástica para articulação no joelho com Synvisc 4 ml", "2200"),
    ("2.01.03.30.1", "Reposição Viscoelástica para articulação no joelho com Synolis", "2200"),
    ("2.01.03.30.1", "Punção Articular Terapêutica-Infiltração com Triancil", "300"),
    ("2.01.03.30.1", "Monovise 4 ml", "2200"),
    ("2.01.03.30.1", "Suprahyal one 20 ml 98 mg", "2200"),
    ("2.01.03.30.1", "Suprahyal Duo", "500"),
    ("2.01.03.30.1", "Euflexxa caixa com 3 ampolas", "1500"),
    ("4.08.01.01-2", "RX-Crânio 2 incidências", "43,74"),
    ("4.08.01.02-0", "RX - Crânio - 3 incidências", "47,62"),
    ("4.08.01.03-9", "RX - Crânio - 4 incidências", "62,46"),
    ("4.08.01.04-7", "RX-Orelha, mastóides ou rochedos - bilateral", "64,48"),
    ("4.08.01.05-5", "RX-Orbitas - bilateral", "47,96"),
    ("4.08.01.06-3", "RX-Seios da face", "45,44"),
    ("4.08.01.07-1", "RX-Sela túrcica", "43,73"),
    ("4.08.01.08-0", "RX-Maxilar inferior", "43,76"),
    ("4.08.01.09-8", "RX-Ossos da face", "47,96"),
    ("4.08.01.10-1", "RX-Arcos zigomáticos ou malar ou apófises estilóides", "45,44"),
    ("4.08.01.11-0", "RX - Articulação temporomandibular bilateral", "47,96"),
    ("4.08.01.12-8", "RX-Adenóides ou cavum", "39,5"),
    ("4.08.01.20-9", "RX-Incidência adicional de crânio ou face", "16,89"),
    ("4.08.02.01-9", "RX-Coluna cervical - 3 incidências", "43,37"),
    ("4.08.02.02-7", "RX-Coluna cervical - 5 incidências", "58,32"),
    ("4.08.02.03-5", "RX-Coluna dorsal - 2 incidências", "47,32"),
    ("4.08.02.04-3", "RX-Coluna dorsal - 4 incidências", "67,23"),
    ("4.08.02.05-1", "RX-Coluna lombo-sacra-3 incidências", "49,15"),
    ("4.08.02.06-0", "RX-Coluna lombo-sacra 5 incidências", "67,23"),
    ("4.08.02.07-8", "RX-Sacro-coccix", "45,63"),
    ("4.08.02.11-6", "RX - Incidência adicional de coluna", "41,94"),
    ("4.08.03.01-5", "RX - Esterno", "45,56"),
    ("4.08.03.02-3", "RX-Articulação esternoclavicular", "43,37"),
    ("4.08.03.03-1", "RX-Costelas por hemitórax", "46,16"),
    ("4.08.03.04-0", "RX-Clavicula", "43,73"),
    ("4.08.03.05-8", "RX - Omoplata ou escapula", "45,56"),
    ("4.08.03.06-6", "RX-Articulação acromioclavicular", "42,28"),
    ("4.08.03.07-4", "RX - Articulação escapuloumeral (ombro)", "42,28"),
    ("4.08.03.08-2", "RX - Braço", "43,73"),
    ("4.08.03.09-0", "RX-Cotovelo", "41,12"),
    ("4.08.03.10-4", "RX - Antebraço", "42,57"),
    ("4.08.03.11-2", "RX - Punho", "43,3"),
    ("4.08.03.12-0", "RX - Mão ou quirodáctilo", "41,12"),
    ("4.08.03.13-9", "RX - Mãos e punhos para idade óssea", "40,76"),
    ("4.08.03.14-7", "RX - Incidência adicional de membro superior", "16,51"),
    ("4.08.04.01-1", "RX - Bacia", "42,83"),
    ("4.08.04.02-0", "RX-Articulações sacroiliacas", "44,53"),
    ("4.08.04.03-8", "RX - Articulação coxofemoral (quadril)", "44,95"),
    ("4.08.04.04-6", "RX-Coxa", "46,16"),
    ("4.08.04.05-4", "RX-Joelho", "44,83"),
    ("4.08.04.06-2", "RX-Patela", "44,83"),
    ("4.08.04.07-0", "RX - Perna", "45"),
    ("4.08.04.08-9", "RX-Articulação tibiotársica (tornozelo)", "41,12"),
    ("4.08.04.09-7", "RX-Pé ou pododáctilo", "42,57"),
    ("4.08.04.10-0", "RX-Calcâneo", "41,12"),
    ("4.08.04.13-5", "RX - Incidência adicional de membro inferior", "16,51"),
]


def _parse_valor(texto: str) -> Decimal:
    s = (texto or "").strip().replace("R$", "").strip()
    if not s:
        raise ValueError("valor vazio")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return Decimal(s)


def _linhas_com_codigo() -> list[tuple[str, str, Decimal]]:
    pares = [(c, d) for c, d, _ in TABELA_RAW]
    codigos = _codigos_unicos(pares)
    if len(codigos) != len(TABELA_RAW):
        raise RuntimeError("contagem de códigos divergente")
    return [
        (codigo, descricao, _parse_valor(valor))
        for (codigo, descricao), (_, _, valor) in zip(codigos, TABELA_RAW, strict=True)
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--empresa-id", type=int, default=EMPRESA_ID_DEFAULT)
    parser.add_argument(
        "--somente-novos",
        action="store_true",
        help="Não atualiza preços já cadastrados neste cabeçalho.",
    )
    args = parser.parse_args()

    if not os.environ.get("DATABASE_URL") and not args.dry_run:
        print("Defina DATABASE_URL ou use --dry-run.", file=sys.stderr)
        return 1

    linhas = _linhas_com_codigo()
    print(f"Linhas: {len(linhas)} | Empresa: {args.empresa_id} | Convênio: {CONVENIO_NOME} | Cabeçalho: {CABECALHO_NOME}")

    if args.dry_run:
        for codigo, descricao, valor in linhas[:5]:
            print(f"  {codigo}\t{valor}\t{descricao[:50]}")
        print("  ...")
        return 0

    import django

    django.setup()
    from empresa.models import Empresa
    from servicos_medicos.models import Cabecalho, Convenio, ServicosMedicos, TabelaPreco

    empresa = Empresa.objects.filter(pk=args.empresa_id).first()
    if not empresa:
        print(f"Empresa id={args.empresa_id} não encontrada.", file=sys.stderr)
        return 1

    convenio, conv_criado = Convenio.objects.get_or_create(
        empresa=empresa,
        nome=CONVENIO_NOME,
    )

    cabecalho = Cabecalho.objects.filter(
        empresa=empresa,
        convenio=convenio,
        nome_tabela__in=[CABECALHO_NOME, CABECALHO_NOME_LEGADO],
    ).first()
    cab_criado = False
    if cabecalho:
        if cabecalho.nome_tabela != CABECALHO_NOME:
            cabecalho.nome_tabela = CABECALHO_NOME
            cabecalho.save(update_fields=["nome_tabela"])
    else:
        cabecalho = Cabecalho.objects.create(
            empresa=empresa,
            convenio=convenio,
            nome_tabela=CABECALHO_NOME,
        )
        cab_criado = True

    print(f"Convênio: {convenio.nome} (id={convenio.pk}, {'criado' if conv_criado else 'existente'})")
    print(f"Cabeçalho: {cabecalho.nome_tabela} (id={cabecalho.pk}, {'criado' if cab_criado else 'existente'})")

    servicos_por_codigo = {s.codigo: s for s in ServicosMedicos.objects.all()}
    existentes = set()
    if args.somente_novos:
        existentes = set(
            TabelaPreco.objects.filter(
                empresa=empresa,
                convenio=convenio,
                cabecalho=cabecalho,
            ).values_list("codigo_servico_id", flat=True)
        )

    criados = atualizados = pulados = faltando = 0
    faltando_lista: list[str] = []

    for codigo, descricao, valor in linhas:
        servico = servicos_por_codigo.get(codigo)
        if not servico:
            faltando += 1
            faltando_lista.append(codigo)
            continue
        if args.somente_novos and servico.pk in existentes:
            pulados += 1
            continue
        _, created = TabelaPreco.objects.update_or_create(
            empresa=empresa,
            convenio=convenio,
            cabecalho=cabecalho,
            codigo_servico=servico,
            defaults={
                "preco_apartamento": valor,
                "preco_enfermaria": valor,
            },
        )
        if created:
            criados += 1
        else:
            atualizados += 1

    total = TabelaPreco.objects.filter(
        empresa=empresa, convenio=convenio, cabecalho=cabecalho
    ).count()
    print(
        f"TabelaPreco criados: {criados} | atualizados: {atualizados} | "
        f"pulados: {pulados} | total cabeçalho: {total}"
    )
    if faltando:
        print(f"AVISO: {faltando} serviço(s) não encontrado(s): {', '.join(faltando_lista[:10])}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
