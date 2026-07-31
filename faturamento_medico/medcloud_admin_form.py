from django import forms

from .models import MedcloudConfig


class MedcloudConfigAdminForm(forms.ModelForm):
    ris_senha = forms.CharField(
        label='Senha RIS',
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text='Deixe em branco para manter a senha já gravada.',
    )
    his_api_key = forms.CharField(
        label='API Key HIS',
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text='Deixe em branco para manter a chave já gravada.',
    )

    class Meta:
        model = MedcloudConfig
        exclude = ('ris_password_cifrada', 'his_api_key_cifrada')
