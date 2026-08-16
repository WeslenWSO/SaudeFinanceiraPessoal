from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='GeminiConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('api_key', models.CharField(
                    blank=True,
                    default='',
                    help_text='Usada em produção se a variável GEMINI_API_KEY não estiver no Render.',
                    max_length=200,
                    verbose_name='API Key Gemini',
                )),
                ('model_name', models.CharField(
                    blank=True,
                    default='gemini-2.5-flash',
                    max_length=80,
                    verbose_name='Modelo Gemini',
                )),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Configuração Gemini',
                'verbose_name_plural': 'Configurações Gemini',
            },
        ),
    ]
