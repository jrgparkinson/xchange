# Generated by Django 3.0.6 on 2020-06-16 22:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0011_auto_20200616_2154'),
    ]

    operations = [
        migrations.AlterField(
            model_name='option',
            name='current_option',
            field=models.CharField(choices=[('B', 'Buy'), ('S', 'Sell')], default='B', max_length=1),
        ),
    ]