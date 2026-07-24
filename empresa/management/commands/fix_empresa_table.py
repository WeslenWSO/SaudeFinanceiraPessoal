from django.core.management.base import BaseCommand
from django.db import connection

class Command(BaseCommand):
    help = 'Corrige a estrutura da tabela empresa'
    
    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            # Adiciona colunas que faltam
            try:
                cursor.execute("ALTER TABLE empresa_empresa ADD COLUMN nome_fantasia VARCHAR(100) NULL")
                self.stdout.write("✓ Coluna 'nome_fantasia' adicionada")
            except Exception as e:
                if "Duplicate column name" in str(e):
                    self.stdout.write("✓ Coluna 'nome_fantasia' já existe")
                else:
                    self.stdout.write(f"✗ Erro ao adicionar 'nome_fantasia': {e}")
            
            try:
                cursor.execute("ALTER TABLE empresa_empresa ADD COLUMN endereco TEXT NULL")
                self.stdout.write("✓ Coluna 'endereco' adicionada")
            except Exception as e:
                if "Duplicate column name" in str(e):
                    self.stdout.write("✓ Coluna 'endereco' já existe")
                else:
                    self.stdout.write(f"✗ Erro ao adicionar 'endereco': {e}")
            
            try:
                cursor.execute("ALTER TABLE empresa_empresa ADD COLUMN telefone VARCHAR(20) NULL")
                self.stdout.write("✓ Coluna 'telefone' adicionada")
            except Exception as e:
                if "Duplicate column name" in str(e):
                    self.stdout.write("✓ Coluna 'telefone' já existe")
                else:
                    self.stdout.write(f"✗ Erro ao adicionar 'telefone': {e}")
            
            try:
                cursor.execute("ALTER TABLE empresa_empresa ADD COLUMN email VARCHAR(254) NULL")
                self.stdout.write("✓ Coluna 'email' adicionada")
            except Exception as e:
                if "Duplicate column name" in str(e):
                    self.stdout.write("✓ Coluna 'email' já existe")
                else:
                    self.stdout.write(f"✗ Erro ao adicionar 'email': {e}")
            
            try:
                cursor.execute("ALTER TABLE empresa_empresa ADD COLUMN data_criacao DATETIME(6) NULL")
                self.stdout.write("✓ Coluna 'data_criacao' adicionada")
            except Exception as e:
                if "Duplicate column name" in str(e):
                    self.stdout.write("✓ Coluna 'data_criacao' já existe")
                else:
                    self.stdout.write(f"✗ Erro ao adicionar 'data_criacao': {e}")
            
            # Cria a tabela UsuarioEmpresa se não existir
            try:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS empresa_usuarioempresa (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        usuario_id INTEGER NOT NULL,
                        empresa_id BIGINT NOT NULL,
                        ativo BOOLEAN NOT NULL DEFAULT 1,
                        data_criacao DATETIME(6) NOT NULL,
                        UNIQUE KEY unique_usuario_empresa (usuario_id, empresa_id)
                    )
                """)
                self.stdout.write("✓ Tabela 'empresa_usuarioempresa' criada/verificada")
            except Exception as e:
                self.stdout.write(f"✗ Erro ao criar tabela 'empresa_usuarioempresa': {e}")
            
            self.stdout.write(self.style.SUCCESS("Estrutura da tabela empresa corrigida!"))













