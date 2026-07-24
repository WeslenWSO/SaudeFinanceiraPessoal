from django.core.management.base import BaseCommand
from django.db import connection

class Command(BaseCommand):
    help = 'Verifica a estrutura da tabela empresa'
    
    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute("DESCRIBE empresa_empresa")
            columns = cursor.fetchall()
            
            self.stdout.write("Estrutura da tabela empresa_empresa:")
            for column in columns:
                self.stdout.write(f"  {column[0]} - {column[1]} - {column[2]} - {column[3]} - {column[4]} - {column[5]}")
            
            # Verifica se as colunas já existem
            column_names = [col[0] for col in columns]
            
            if 'nome_fantasia' in column_names:
                self.stdout.write("✓ Coluna 'nome_fantasia' já existe")
            else:
                self.stdout.write("✗ Coluna 'nome_fantasia' não existe")
                
            if 'data_criacao' in column_names:
                self.stdout.write("✓ Coluna 'data_criacao' já existe")
            else:
                self.stdout.write("✗ Coluna 'data_criacao' não existe")
                
            if 'data_atualizacao' in column_names:
                self.stdout.write("✓ Coluna 'data_atualizacao' já existe")
            else:
                self.stdout.write("✗ Coluna 'data_atualizacao' não existe")













