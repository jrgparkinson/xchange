# Generated by Django 3.0.6 on 2020-06-16 21:53

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0009_option_option_holder'),
    ]

    operations = [
        migrations.AlterField(
            model_name='option',
            name='option_holder',
            field=models.ForeignKey(blank=True, on_delete=django.db.models.deletion.CASCADE, related_name='app_option_option_holder', to='app.Entity'),
        ),
    ]
