# Generated by Django 3.0.6 on 2020-05-27 21:41

import datetime
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Asset',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_virtual', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='Athlete',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('power_of_10', models.URLField()),
            ],
        ),
        migrations.CreateModel(
            name='Auction',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('description', models.TextField()),
                ('start_date', models.DateTimeField()),
                ('end_date', models.DateTimeField()),
            ],
        ),
        migrations.CreateModel(
            name='Club',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='Entity',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('capital', models.FloatField(default=1000)),
            ],
        ),
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('date', models.DateField()),
            ],
        ),
        migrations.CreateModel(
            name='Race',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('time', models.DateTimeField()),
                ('results_link', models.URLField()),
                ('event_details_link', models.URLField()),
                ('max_dividend', models.FloatField()),
                ('min_dividend', models.FloatField(default=10.0)),
                ('num_competitors', models.IntegerField(blank=True, null=True)),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='app_race_event', to='app.Event')),
            ],
        ),
        migrations.CreateModel(
            name='Season',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('O', 'Open'), ('S', 'Suspended')], default='O', max_length=1)),
                ('name', models.CharField(max_length=100)),
                ('start_time', models.DateTimeField()),
                ('end_time', models.DateTimeField()),
            ],
        ),
        migrations.CreateModel(
            name='Bank',
            fields=[
                ('entity_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='app.Entity')),
                ('name', models.CharField(max_length=100)),
            ],
            bases=('app.entity',),
        ),
        migrations.CreateModel(
            name='Future',
            fields=[
                ('asset_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='app.Asset')),
                ('strike_price', models.FloatField()),
                ('action_date', models.DateTimeField()),
            ],
            bases=('app.asset',),
        ),
        migrations.CreateModel(
            name='Investor',
            fields=[
                ('entity_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='app.Entity')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            bases=('app.entity',),
        ),
        migrations.CreateModel(
            name='TransactionHistory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ammount', models.FloatField()),
                ('reason', models.TextField()),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('recipient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='app_transactionhistory_to', to='app.Entity')),
                ('sender', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='app_transactionhistory_from', to='app.Entity')),
            ],
        ),
        migrations.CreateModel(
            name='Trade',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('price', models.FloatField()),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('decision_dt', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(choices=[('P', 'Pending'), ('A', 'Accepted'), ('R', 'Rejected'), ('C', 'Cancelled')], default='P', max_length=1)),
                ('asset', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='app_trade_asset', to='app.Asset')),
                ('buyer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='app_trade_buyer', to='app.Entity')),
                ('creator', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='app_trade_creator', to='app.Entity')),
                ('season', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='app.Season')),
                ('seller', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='app_trade_seller', to='app.Entity')),
            ],
        ),
        migrations.CreateModel(
            name='Team',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('club', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='app.Club')),
            ],
        ),
        migrations.CreateModel(
            name='Result',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('position', models.IntegerField()),
                ('time', models.DurationField()),
                ('dividend', models.FloatField()),
                ('dividend_distributed', models.BooleanField(default=False)),
                ('athlete', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='app_result_athlete', to='app.Athlete')),
                ('race', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='app.Race')),
            ],
        ),
        migrations.CreateModel(
            name='Lot',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('volume', models.FloatField()),
                ('athlete', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='app_lot_athlete', to='app.Athlete')),
            ],
        ),
        migrations.CreateModel(
            name='Loan',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('last_processed', models.DateTimeField(auto_now_add=True)),
                ('next_payment_due', models.DateTimeField()),
                ('interest_rate', models.FloatField()),
                ('balance', models.FloatField()),
                ('repayment_interval', models.DurationField(default=datetime.timedelta(7))),
                ('lender', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='app_loan_lender', to='app.Entity')),
                ('recipient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='app_loan_recipient', to='app.Entity')),
                ('season', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='app.Season')),
            ],
        ),
        migrations.AddField(
            model_name='event',
            name='season',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='app.Season'),
        ),
        migrations.CreateModel(
            name='Debt',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('ammount', models.FloatField()),
                ('owed_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='app_debt_owed_by', to='app.Entity')),
                ('owed_to', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='app_debt_owed_to', to='app.Entity')),
            ],
        ),
        migrations.CreateModel(
            name='Bid',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('P', 'Pending'), ('A', 'Accepted'), ('R', 'Rejected')], default='P', max_length=1)),
                ('volume', models.FloatField()),
                ('price_per_volume', models.FloatField()),
                ('auction', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='app.Auction')),
                ('bidder', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='app_bid_bidder', to='app.Entity')),
                ('lot', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='app.Lot')),
            ],
        ),
        migrations.AddField(
            model_name='auction',
            name='season',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='app.Season'),
        ),
        migrations.AddField(
            model_name='athlete',
            name='club',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='app.Club'),
        ),
        migrations.AddField(
            model_name='athlete',
            name='team_last_year',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='app.Team'),
        ),
        migrations.AddField(
            model_name='asset',
            name='owner',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='app_asset_owner', to='app.Entity'),
        ),
        migrations.AddField(
            model_name='asset',
            name='season',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='app.Season'),
        ),
        migrations.CreateModel(
            name='Option',
            fields=[
                ('future_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='app.Future')),
                ('current_option', models.BooleanField(default=True)),
            ],
            bases=('app.future',),
        ),
        migrations.CreateModel(
            name='Swap',
            fields=[
                ('asset_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='app.Asset')),
                ('a_to_b_payment', models.TextField()),
                ('b_to_a_payment', models.TextField()),
                ('party_a', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='app_swap_partya', to='app.Investor')),
                ('party_b', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='app_swap_partyb', to='app.Investor')),
            ],
            bases=('app.asset',),
        ),
        migrations.CreateModel(
            name='Share',
            fields=[
                ('asset_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='app.Asset')),
                ('volume', models.FloatField()),
                ('athlete', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='app_share_athlete', to='app.Athlete')),
            ],
            bases=('app.asset',),
        ),
    ]
