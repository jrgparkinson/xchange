# Generated by Django 3.0.6 on 2020-06-10 17:46

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0004_loanoffer'),
    ]

    operations = [
        migrations.AlterField(
            model_name='loan',
            name='interest_rate',
            field=models.FloatField(help_text='Fractional interest rate'),
        ),
        migrations.AlterField(
            model_name='loanoffer',
            name='interest_rate',
            field=models.FloatField(help_text='Fractional interest rate'),
        ),
        migrations.CreateModel(
            name='BankOffer',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('volume', models.FloatField()),
                ('total_price', models.FloatField()),
                ('athlete', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='app.Athlete')),
                ('bank', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='app.Bank')),
                ('season', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='app.Season')),
            ],
        ),
    ]
