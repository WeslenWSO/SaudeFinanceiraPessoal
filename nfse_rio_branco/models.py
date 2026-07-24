# nfse_rio_branco/models.py
from django.db import models
from django.utils import timezone

class Company(models.Model):
    nome = models.CharField(max_length=120)
    cnpj = models.CharField(max_length=14, db_index=True)
    inscricao_municipal = models.CharField(max_length=30, blank=True, null=True)


    def __str__(self):
        return f"{self.nome} ({self.cnpj})"


# class PortalCredential(models.Model):
#       company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name="cred")
#       usuario = models.CharField(max_length=120)
#       senha = models.CharField(max_length=255) # Em produção: criptografe/guarde em cofre


      # def __str__(self):
      #     return f"Login portal – {self.company}"


class DownloadJob(models.Model):
      class Status(models.TextChoices):
          PENDENTE = "PENDENTE", "Pendente"
          EM_ANDAMENTO = "EM_ANDAMENTO", "Em andamento"
          CONCLUIDO = "CONCLUIDO", "Concluído"
          ERRO = "ERRO", "Erro"


      company = models.ForeignKey(Company, on_delete=models.CASCADE)
      inicio = models.DateField()
      fim = models.DateField()
      
      status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDENTE)
      criado_em = models.DateTimeField(default=timezone.now)
      log = models.TextField(blank=True, default="")


      def append_log(self, msg: str):
         self.log += f"[{timezone.now().isoformat()}] {msg}\n"
         self.save(update_fields=["log"])


class Nfse(models.Model):
     company = models.ForeignKey(Company, on_delete=models.CASCADE)
     numero = models.CharField(max_length=30)
     serie = models.CharField(max_length=10, blank=True, null=True)
     codigo_verificacao = models.CharField(max_length=64, blank=True, null=True)
     data_emissao = models.DateTimeField(blank=True, null=True)
     competencia = models.CharField(max_length=7, blank=True, null=True) # AAAA-MM
     valor_servico = models.DecimalField(max_digits=15, decimal_places=2, default=0)
     iss_retido = models.BooleanField(default=False)
     prestador_cnpj = models.CharField(max_length=14, blank=True, null=True)
     tomador_cnpj_cpf = models.CharField(max_length=14, blank=True, null=True)
     xml = models.TextField()
     sha1 = models.CharField(max_length=40, unique=True) # hash p/ idempotência
     criado_em = models.DateTimeField(auto_now_add=True)


     class Meta:
        unique_together = ("company", "numero", "serie")


     def __str__(self):
        return f"NFS-e {self.numero}/{self.serie or '-'}"

class PortalCredential(models.Model):
   company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name="cred")
   usuario = models.CharField(max_length=120)
   senha = models.CharField(max_length=255)
#  WebService
   senha_ws = models.CharField(max_length=120, blank=True, null=True)
   im = models.CharField("Inscrição Municipal", max_length=30, blank=True, null=True)
   ws_homologa = models.BooleanField(default=True)
   def __str__(self):
          return f"Login portal – {self.company}"
