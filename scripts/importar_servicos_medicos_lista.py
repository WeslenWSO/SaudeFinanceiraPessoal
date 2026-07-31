#!/usr/bin/env python
"""
Importa lista de serviços médicos (código + descrição) para ServicosMedicos.

  set DATABASE_URL=postgresql://...
  python scripts/importar_servicos_medicos_lista.py
  python scripts/importar_servicos_medicos_lista.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")

# (código bruto, descrição) — códigos duplicados ou "-" recebem sufixo automático
SERVICOS_RAW: list[tuple[str, str]] = [
    ("41301323", "Tonometria"),
    ("40103137", "Campimetria"),
    ("41301080", "Cerastoscopia/Topografia Corneá"),
    ("41301129", "Curva Tensional Diária"),
    ("41301242", "Gonioscopia"),
    ("41301250", "Mapeamento de Retina"),
    ("41301269", "Microscopia Especular"),
    ("41301307", "PAM/Potencial de Acuidade Visual"),
    ("41301315", "Retinografia"),
    ("41501012", "Biometria ultrassônica-Ecobiometria"),
    ("41501128", "Paquimetria"),
    ("40901017", "USG Globo Ocular"),
    ("41501144", "Tomografia de Coerência Óptica"),
    ("30306019", "Capsulotomia"),
    ("30306027", "Facectomia com implante de lente monofocal"),
    ("30303010", "Transplante de Membrana Aminiótica"),
    ("30303109", "Exerese de Tumor de Conjuntiva"),
    ("30303010", "Pterígio + Transplante de Membrana"),
    ("30301190", "Ressecção de Tumor Palpebral"),
    ("30304105", "Cirurgia Refrativa Convencional"),
    ("40201120", "Endoscopia Digestiva Alta sem Biópsia"),
    ("40202615", "Endoscopia digestiva alta com biópsia e teste de urease"),
    ("40202038", "Endoscopia digestiva alta com biópsia e/ou citologia"),
    ("40201082", "Colonoscopia (Retossigmoidoscopia)"),
    ("40202666", "Colonoscopia com biópsia e citopatologia"),
    ("40202712", "Colonoscopia com mucosectomia"),
    ("30911079", "Cateterismo Cardíaco"),
    ("30912105", "Angioplastia Coronária com 1 stent convencional"),
    ("30912105", "Angioplastia Coronária com 2 stent convencional"),
    ("30912105", "Angioplastia Coronária com 1 stent farmacologia"),
    ("30912105", "Angioplastia Coronária com 2 stent farmacologia"),
    ("-", "STENT CONVENCIONAL ADICIONAL"),
    ("-", "STENT FARMACOLÓGICO ADICIONAL"),
    ("40201198", "Vídeo endoscopia do esfincter velo-palatino com ótica flexível"),
    ("40201210", "Video- endoscopia naso- sinusal com ótica flexivel"),
    ("40201252", "Video- faringo laringoscopia com endoscópio flexivel"),
    ("40201260", "Video- faringo laringoscopia com endoscópio flexível"),
    ("4021236", "Vídeo- laringo estroboscopia com endoscópio flexivel"),
    ("40201244", "Videolaringo estroboscopia com endoscópio flexível"),
    ("20104065", "Cerumen- remoção- unilateral"),
    ("30501083", "Corpo estranhos retirada em consultório (nariz)"),
    ("40103013", "Análise computadorizada de voz"),
    ("40103021", "Análise computadorizada de papila e/ou fibras nervosas monocular"),
    ("40103030", "Análise computadorizada do segmento anterior monocular"),
    ("40103064", "Audiometria de tronco cerebral (PEA) BERA"),
    ("40103064", "Audiometria de tronco cerebral (PEA) BERA EM CENTRO CIRÚRGICO"),
    ("40103510", "Polissonografia"),
    ("40103072", "Audiometria Tonal"),
    ("40103080", "Audiometria Tonal limiar infantil condicionada"),
    ("40103099", "Audiometria vocal pesquisa de limiar de discriminação"),
    ("40103102", "Audiometria vocal pesquisa de limiar de inteligibilidade"),
    ("40103420", "Imitanciometria de alta frequência"),
    ("40103439", "Impedanciometria timpanometria"),
    ("40103455", "Otoemissões acústicas produtos de distorção"),
    ("40103749", "Vectoeletronistagmografia computadorizada"),
    ("31101577", "Nefrolitotripsia percutânea unilateral a laser"),
    ("31102050", "Colocação distópica de duplo J unilateral"),
    ("31102360", "Ureterorrenolitotripsia flexível a laser unilateral colocação de Duplo J"),
    ("31102565", "Ureterorrenal Litotripsia rigida unilateral a laser"),
    ("31103472", "Retirada endoscópica de duplo J"),
    ("31103472", "Ressecção endoscópica da próstata"),
    ("31103456", "Tumor vesical ressecção endoscópica"),
    ("31103359", "Incontinência urinária -tratamento cirúrgico suprapúbico"),
    ("31103561", "Cistolitotripsia a laser"),
    ("31104223", "Uretrotomia interna"),
    ("40201066", "Cistoscopia e/ou uretroscopia"),
    ("31203043", "Hidrocele unilateral- correção cirúrgica"),
    ("31203043", "Hidrocele bilateral- correção cirúrgica"),
    ("31023078", "Orquiectomia unilateral"),
    ("31203108", "Torção de testiculo- cura cirúrgica"),
    ("31203124", "Varicocele unilateral- correção cirúrgica"),
    ("31206220", "Postectomia"),
    ("31205046", "Vasectomia bilateral"),
    ("41001230", "Tomografia computadorizada diagnóstica-Angiotomografia coronariana"),
    ("40103234", "SISTEMA NERVOSO EEGQ quantitativo (mapeamento Cerebral)"),
    ("20104189", "Sessão de Oxigenoterapia Hiperbarica"),
    ("31602274", "Anestesia para exames de Tomografia Computadorizada"),
    ("31602282", "Anestesia para exames de Ressonância Magnética"),
    ("2.01.03.30.1", "Reposição Viscoelástica para articulação no joelho com Synvisc One 6ml"),
    ("2.01.03.30.1", "Reposição Viscoelástica para articulação no joelho com Synvisc 4 ml"),
    ("2.01.03.30.1", "Reposição Viscoelástica para articulação no joelho com Synolis"),
    ("2.01.03.30.1", "Punção Articular Terapêutica-Infiltração com Triancil"),
    ("2.01.03.30.1", "Monovise 4 ml"),
    ("2.01.03.30.1", "Suprahyal one 20 ml 98 mg"),
    ("2.01.03.30.1", "Suprahyal Duo"),
    ("2.01.03.30.1", "Euflexxa caixa com 3 ampolas"),
    ("4.08.01.01-2", "RX-Crânio 2 incidências"),
    ("4.08.01.02-0", "RX - Crânio - 3 incidências"),
    ("4.08.01.03-9", "RX - Crânio - 4 incidências"),
    ("4.08.01.04-7", "RX-Orelha, mastóides ou rochedos - bilateral"),
    ("4.08.01.05-5", "RX-Orbitas - bilateral"),
    ("4.08.01.06-3", "RX-Seios da face"),
    ("4.08.01.07-1", "RX-Sela túrcica"),
    ("4.08.01.08-0", "RX-Maxilar inferior"),
    ("4.08.01.09-8", "RX-Ossos da face"),
    ("4.08.01.10-1", "RX-Arcos zigomáticos ou malar ou apófises estilóides"),
    ("4.08.01.11-0", "RX - Articulação temporomandibular bilateral"),
    ("4.08.01.12-8", "RX-Adenóides ou cavum"),
    ("4.08.01.20-9", "RX-Incidência adicional de crânio ou face"),
    ("4.08.02.01-9", "RX-Coluna cervical - 3 incidências"),
    ("4.08.02.02-7", "RX-Coluna cervical - 5 incidências"),
    ("4.08.02.03-5", "RX-Coluna dorsal - 2 incidências"),
    ("4.08.02.04-3", "RX-Coluna dorsal - 4 incidências"),
    ("4.08.02.05-1", "RX-Coluna lombo-sacra-3 incidências"),
    ("4.08.02.06-0", "RX-Coluna lombo-sacra 5 incidências"),
    ("4.08.02.07-8", "RX-Sacro-coccix"),
    ("4.08.02.11-6", "RX - Incidência adicional de coluna"),
    ("4.08.03.01-5", "RX - Esterno"),
    ("4.08.03.02-3", "RX-Articulação esternoclavicular"),
    ("4.08.03.03-1", "RX-Costelas por hemitórax"),
    ("4.08.03.04-0", "RX-Clavicula"),
    ("4.08.03.05-8", "RX - Omoplata ou escapula"),
    ("4.08.03.06-6", "RX-Articulação acromioclavicular"),
    ("4.08.03.07-4", "RX - Articulação escapuloumeral (ombro)"),
    ("4.08.03.08-2", "RX - Braço"),
    ("4.08.03.09-0", "RX-Cotovelo"),
    ("4.08.03.10-4", "RX - Antebraço"),
    ("4.08.03.11-2", "RX - Punho"),
    ("4.08.03.12-0", "RX - Mão ou quirodáctilo"),
    ("4.08.03.13-9", "RX - Mãos e punhos para idade óssea"),
    ("4.08.03.14-7", "RX - Incidência adicional de membro superior"),
    ("4.08.04.01-1", "RX - Bacia"),
    ("4.08.04.02-0", "RX-Articulações sacroiliacas"),
    ("4.08.04.03-8", "RX - Articulação coxofemoral (quadril)"),
    ("4.08.04.04-6", "RX-Coxa"),
    ("4.08.04.05-4", "RX-Joelho"),
    ("4.08.04.06-2", "RX-Patela"),
    ("4.08.04.07-0", "RX - Perna"),
    ("4.08.04.08-9", "RX-Articulação tibiotársica (tornozelo)"),
    ("4.08.04.09-7", "RX-Pé ou pododáctilo"),
    ("4.08.04.10-0", "RX-Calcâneo"),
    ("4.08.04.13-5", "RX - Incidência adicional de membro inferior"),
]

MAX_CODIGO = 20
MAX_SERVICO = 200


def _codigos_unicos(rows: list[tuple[str, str]]) -> list[tuple[str, str]]:
    vistos: dict[str, int] = {}
    sem_codigo = 0
    resultado: list[tuple[str, str]] = []

    for bruto, descricao in rows:
        bruto = (bruto or "").strip()
        descricao = descricao.strip()[:MAX_SERVICO]

        if not bruto or bruto == "-":
            sem_codigo += 1
            codigo = f"SC-{sem_codigo:03d}"
        else:
            n = vistos.get(bruto, 0)
            vistos[bruto] = n + 1
            codigo = bruto if n == 0 else f"{bruto}-{n + 1}"
            if len(codigo) > MAX_CODIGO:
                codigo = codigo[:MAX_CODIGO]

        resultado.append((codigo, descricao))

    return resultado


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not os.environ.get("DATABASE_URL") and not args.dry_run:
        print("Defina DATABASE_URL ou use --dry-run.", file=sys.stderr)
        return 1

    import django

    django.setup()
    from servicos_medicos.models import ServicosMedicos

    servicos = _codigos_unicos(SERVICOS_RAW)
    print(f"Total na lista: {len(servicos)}")

    criados = 0
    atualizados = 0
    for codigo, descricao in servicos:
        if args.dry_run:
            print(f"  {codigo}\t{descricao[:60]}")
            continue
        obj, created = ServicosMedicos.objects.update_or_create(
            codigo=codigo,
            defaults={"servicos": descricao},
        )
        if created:
            criados += 1
        else:
            atualizados += 1

    if args.dry_run:
        return 0

    total = ServicosMedicos.objects.count()
    print(f"Criados: {criados} | Atualizados: {atualizados} | Total no banco: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
