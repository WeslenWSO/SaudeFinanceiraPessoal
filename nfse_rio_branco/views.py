
# nfse_rio_branco/views.py
from django.views.generic import FormView
from django.urls import reverse_lazy
from django.contrib import messages
from .forms import StartDownloadForm
import subprocess, sys
from django.shortcuts import render
from django.http.response import Http404
from .models import Company


#class StartDownloadView(FormView):
#      template_name = "nfse_rio_branco/start_download.html"
#      form_class = StartDownloadForm
#      success_url = reverse_lazy("nfse_rio_branco:start")


#      def form_valid(self, form):
#          c = form.cleaned_data['company']
#          ini = form.cleaned_data['inicio'].strftime('%d/%m/%Y')
#          fim = form.cleaned_data['fim'].strftime('%d/%m/%Y')
#          opcao = form.cleaned_data['opcao']
#          # dispara comando síncrono (para simplificar)
         
#          if opcao == 1:
#             opcao = 1
#          else: 
#             opcao =0
         
#          print(opcao)
            
#          if opcao == 0:     
#             #   cmd = [sys.executable, "manage.py", "fetch_rio_branco_nfse", "--company", str(c.id), "--inicio", ini, "--fim", fim, "--headless"]
#               cmd = [sys.executable, "manage.py", "fetch_rio_branco_ws_nfse", "--company", str(c.id), "--inicio", ini, "--fim", fim, "--headless"]
#          if opcao == 1:
#               cmd = [sys.executable, "manage.py", "fetch_rio_branco_ws_nfse", "--company", str(c.id), "--inicio", ini, "--fim", fim, "--headless"]
#          try:
#             subprocess.check_call(cmd)
#             messages.success(self.request, "Coleta concluída. Veja Relatórios/Exportações.")
#          except subprocess.CalledProcessError as e:
#             messages.error(self.request, f"Falha na coleta: {e}")
#          return super().form_valid(form)


# views.py
import sys, subprocess
from django.shortcuts import render
from django.http import Http404
from .models import Company, DownloadJob

def start1(request):
    if request.method == 'GET':
        # Mostra o formulário com a lista de empresas
        companies = Company.objects.all().order_by('nome')
        return render(request, 'nfse_rio_branco/start.html', {'companies': companies})

    # POST: processa
    company_id = request.POST.get('company')  # string
    inicio = request.POST.get('inicio')       # "DD/MM/AAAA"
    fim    = request.POST.get('fim')          # "DD/MM/AAAA"
    opcao  = request.POST.get('opcao')        # "1" portal | "2" ws municipal | "3" ws nacional

    if not company_id:
        return render(request, 'nfse_rio_branco/start.html', {
            'error': 'Selecione a empresa.',
            'companies': Company.objects.all().order_by('nome'),
        })

    try:
        company = Company.objects.get(pk=company_id)
    except Company.DoesNotExist:
        # Ao invés de 404, mostre mensagem na própria página
        return render(request, 'nfse_rio_branco/start.html', {
            'error': f'Empresa ID {company_id} não encontrada.',
            'companies': Company.objects.all().order_by('nome'),
        })

    # Monta o comando certo
    if opcao == '1':
        cmd = [
            sys.executable, 'manage.py', 'fetch_rio_branco_nfse',
            '--company', str(company.pk),
            '--inicio', inicio,
            '--fim', fim,
            '--headless'  # só para o portal (navegador)
        ]
    else:
        base = 'nacional' if opcao == '3' else 'municipal'
        cmd = [
            sys.executable, 'manage.py', 'fetch_rio_branco_ws_nfse',
            '--company', str(company.pk),
            '--inicio', inicio,
            '--fim', fim,
            '--base', base,
        ]

    # Executa em background
    subprocess.Popen(cmd)

    # Redireciona para página de status
    from django.shortcuts import redirect
    return redirect('nfse_rio_branco:status')


def status_view(request):
    # Mostra os últimos jobs
    jobs = DownloadJob.objects.all().order_by('-criado_em')[:10]  # últimos 10
    return render(request, 'nfse_rio_branco/status.html', {'jobs': jobs})
