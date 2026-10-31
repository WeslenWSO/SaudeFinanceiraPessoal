from django import forms

from accounts.models import BackupBancoConfig


class BackupBancoConfigForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in (
            'horario_1_ativo',
            'horario_2_ativo',
            'backup_automatico_ativo',
            'gerar_tarefas_agendador',
        ):
            self.fields[name].widget.attrs.setdefault('class', 'form-check-input')

    class Meta:
        model = BackupBancoConfig
        fields = [
            'drive_pasta_nome',
            'drive_folder_id',
            'horario_1',
            'horario_1_ativo',
            'horario_2',
            'horario_2_ativo',
            'backup_automatico_ativo',
            'gerar_tarefas_agendador',
            'responsavel_tarefa',
            'dias_tarefas_frente',
        ]
        widgets = {
            'horario_1': forms.TimeInput(format='%H:%M', attrs={'type': 'time', 'class': 'form-control'}),
            'horario_2': forms.TimeInput(format='%H:%M', attrs={'type': 'time', 'class': 'form-control'}),
            'drive_pasta_nome': forms.TextInput(attrs={'class': 'form-control'}),
            'drive_folder_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '1f6ULWD8aAPS5gfG7mGwY2GbG_HrQgz4y'}),
            'responsavel_tarefa': forms.TextInput(attrs={'class': 'form-control'}),
            'dias_tarefas_frente': forms.NumberInput(attrs={'class': 'form-control', 'min': 7, 'max': 730}),
        }

    def clean_drive_folder_id(self):
        val = (self.cleaned_data.get('drive_folder_id') or '').strip()
        if not val:
            raise forms.ValidationError('Informe o ID da pasta no Google Drive.')
        if 'drive.google.com' in val and '/folders/' in val:
            val = val.split('/folders/')[-1].split('?')[0].strip('/')
        return val

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('horario_1_ativo') and cleaned.get('horario_2_ativo'):
            h1 = cleaned.get('horario_1')
            h2 = cleaned.get('horario_2')
            if h1 and h2 and h1 == h2:
                raise forms.ValidationError(
                    'Os dois horários não podem ser iguais quando ambos estão ativos.'
                )
        if not cleaned.get('horario_1_ativo') and not cleaned.get('horario_2_ativo'):
            if cleaned.get('backup_automatico_ativo') or cleaned.get('gerar_tarefas_agendador'):
                raise forms.ValidationError(
                    'Ative pelo menos um horário para backup ou lembretes.'
                )
        return cleaned
