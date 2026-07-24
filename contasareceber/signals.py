from django.db.models.signals import post_save
from django.dispatch import receiver

from notasfiscais.models import NotaFiscalServico


@receiver(post_save, sender=NotaFiscalServico)
def sync_socio_nf_para_contas_receber(sender, instance, **kwargs):
    """Ao gravar a NF (incl. sócio), alinha o sócio em todas as parcelas (CAR) vinculadas."""
    from .socio_sync import propagar_socio_nota_para_contas_receber

    propagar_socio_nota_para_contas_receber(instance)
