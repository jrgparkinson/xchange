# Generated by Django 3.0.6 on 2020-06-19 19:06

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0014_auto_20200616_2312'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='trade',
            name='decision_dt',
        ),
    ]
