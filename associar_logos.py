#!/usr/bin/env python
"""
Script para associar logos aos bancos baseado nos arquivos na pasta media/logobanco/
"""
import os
import sys
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
django.setup()

from extrato.models import Banco

def associar_logos():
    from django.conf import settings

    logos_dir = os.path.join(settings.MEDIA_ROOT, 'logobanco')

    if not os.path.exists(logos_dir):
        print(f"Diretório {logos_dir} não existe!")
        return

    print(f"Procurando logos em: {logos_dir}")

    # Mapeamento manual para casos especiais
    mapeamento_manual = {
        'SICOOB_Rjb7Izm.jpg': '756',  # SICOOB
        'SICOOB.jpg': '756',  # SICOOB alternativo
        '237.png': '237',  # Bradesco
        '104.png': '104',
        'caixa.png': '104',
        '999.png': '999',
        '707.png': '707',
        'daycoval.png': '707',
        '001_AKnK77y.png': '001',  # Banco do Brasil
        '001_bMaOKoZ.png': '001',  # Banco do Brasil alternativo
        '001.png': '001',  # Banco do Brasil
        'basa.jpg': '003',  # BASA
        'carteira.jpg': '000'  # Carteira (conta caixa)
    }

    arquivos_processados = 0

    for filename in os.listdir(logos_dir):
        if not filename.endswith(('.png', '.jpg', '.jpeg')):
            continue

        # Tentar extrair código do nome do arquivo
        code = None

        # Primeiro, verificar mapeamento manual
        if filename in mapeamento_manual:
            code = mapeamento_manual[filename]
        else:
            # Tentar extrair do início do nome
            parts = filename.split('_')[0].split('.')[0]
            if parts.isdigit() and len(parts) == 3:
                code = parts

        if not code:
            print(f"Não foi possível determinar código para: {filename}")
            continue

        try:
            banco = Banco.objects.get(codigo=code)
            banco.logo = f'logobanco/{filename}'
            banco.save()
            print(f"[OK] Associado {filename} ao banco {banco.nome} (codigo: {code})")
            arquivos_processados += 1
        except Banco.DoesNotExist:
            print(f"[ERRO] Banco com codigo {code} nao encontrado para {filename}")
        except Exception as e:
            print(f"[ERRO] Erro ao processar {filename}: {e}")

    print(f"\nProcessamento concluído! {arquivos_processados} logos associados.")

if __name__ == '__main__':
    associar_logos()