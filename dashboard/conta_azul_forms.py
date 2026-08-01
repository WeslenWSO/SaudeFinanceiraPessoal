from django import forms

from dashboard.models import ContaAzulConfig


class ContaAzulConfigForm(forms.ModelForm):
    client_secret = forms.CharField(
        label='Client Secret',
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text='Deixe em branco para manter o secret já gravado.',
    )

    class Meta:
        model = ContaAzulConfig
        fields = (
            'ativo',
            'ambiente',
            'client_id',
            'redirect_uri',
        )
        widgets = {
            'client_id': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
            'redirect_uri': forms.TextInput(attrs={'class': 'form-control'}),
            'ambiente': forms.Select(attrs={'class': 'form-select'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not (self.instance.redirect_uri or '').strip():
            self.fields['redirect_uri'].initial = self.instance.redirect_uri_efetiva()

    def save(self, commit=True):
        obj = super().save(commit=False)
        secret = self.cleaned_data.get('client_secret') or ''
        if secret.strip():
            from dashboard.conta_azul.config import gravar_client_secret
            gravar_client_secret(obj, secret)
        if commit:
            obj.save()
        return obj
