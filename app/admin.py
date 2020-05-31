from django.contrib import admin
from .models import *
from django.contrib import messages
from import_export.admin import ImportExportModelAdmin, ImportForm, ConfirmImportForm, ImportMixin
from import_export import resources
from import_export.fields import Field
from import_export.widgets import ForeignKeyWidget
from .import_from_web import lookup_po10, load_po10_results
from django import forms
from bs4 import BeautifulSoup
import re
import urllib.request
from import_export.results import RowResult


admin.site.register(Event)
admin.site.register(Season)




class ShareInline(admin.TabularInline):
    model = Share

class BankAdmin(admin.ModelAdmin):
    inlines = [ ShareInline,  ]
admin.site.register(Bank, BankAdmin)

class InvestorAdmin(admin.ModelAdmin):
    inlines = [ ShareInline,  ]
admin.site.register(Investor, InvestorAdmin)

class AthleteNotFound(Exception):
    pass

class ResultExists(Exception):
    pass

class AthleteForeignKeyWidget(ForeignKeyWidget):
    def get_queryset(self, value, row):
        try:
            print("Try and get athlete")
            a = self.model.objects.filter(
                name=row["athlete"],
            )
            # print(a)
            if len(a) == 0:
                raise AthleteNotFound(row["athlete"])
            
            return a

        except Athlete.DoesNotExist:
            # print("Athlete does not exist")
            raise AthleteNotFound(row["athlete"])


class ResultResource(resources.ModelResource):
    """ Example CSV import:

    athlete,position,time
Jamie Parkinson,10,00:30:00
    """

    athlete = Field(
        column_name='athlete',
        attribute='athlete',
        # widget=ForeignKeyWidget(Athlete, 'name'))
        widget = AthleteForeignKeyWidget(Athlete, 'name'))

    # Fill id column
    def before_import(self, dataset, using_transactions, dry_run, **kwargs):
        print("Before import")
        
        dataset.insert_col(0, col=["",]*dataset.height, header="id")
        print(dataset)

    def __init__(self, request=None):
        super()
        self.request = request

    def get_field_names(self):
        names = []
        for field in self.get_fields():
            names.append(self.get_field_name(field))
        return names

    def import_row(self, row, instance_loader, **kwargs):
        # https://github.com/django-import-export/django-import-export/issues/763
        # overriding import_row to ignore errors and skip rows that fail to import
        # without failing the entire import
        import_result = super(ResultResource, self).import_row(row, instance_loader, **kwargs)
        # if import_result.import_type == RowResult.IMPORT_TYPE_ERROR:
        #     # Copy the values to display in the preview report
        #     import_result.diff = [row[val] for val in row]
        #     # Add a column with the error message
        #     # import_result.diff[1] = "Athlete not found: " + row[]
        #     import_result.diff.append('Errors: {}'.format([err.error for err in import_result.errors]))
        #     # clear errors and mark the record to skip
        #     import_result.errors = []
        #     import_result.import_type = RowResult.IMPORT_TYPE_SKIP

        # return import_result

        if import_result.import_type == RowResult.IMPORT_TYPE_ERROR:
            import_result.diff = [
                row.get(name, '') for name in self.get_field_names()
            ]

            # Add a column with the error message
            import_result.diff.append(
                "Errors: {}".format(
                    [err.error for err in import_result.errors]
                )
            )
            # clear errors and mark the record to skip
            import_result.errors = []
            import_result.import_type = RowResult.IMPORT_TYPE_SKIP

        return import_result

    def before_import_row(self, row, **kwargs):
        # row['race'] = self.race
        print("before row import")

        race = self.request.POST.get('race', None)
        if race:
            print(race)
            self.request.session['import_context_race'] = race
        else:
            print("error")
            # if this raises a KeyError, we want to know about it.
            # It means that we got to a point of importing data without
            # contract context, and we don't want to continue.
            try:
                sector = self.request.session['import_context_race']
            except KeyError as e:
                raise Exception("Race context failure on row import, " +
                                    f"check resources.py for more info: {e}")
        row['race'] = race


        # existing_row = Result.objects.all().filter(Q(race=race) & Q(athlete=row['athlete']))
        # if len(existing_row) > 0:
        #     raise ResultExists()

    def get_instance(self, instance_loader, row):
        return False

    class Meta:
        # fields
        model=Result
        fields = ('athlete', 'race', 'position', 'time', )
        # import_id_fields = ('name',)
        raise_errors=False
        skip_unchanged=True
        report_skipped=True

class ResultAdmin(ImportExportModelAdmin):
    resource_class = ResultResource


class RaceImportForm(ImportForm):
    race = forms.ModelChoiceField(required=True,queryset=Race.objects.all())

class ConfirmRaceImportForm(ConfirmImportForm):
    race = forms.ModelChoiceField(required=True,queryset=Race.objects.all())

class CustomResultAdmin(ImportExportModelAdmin):
    resource_class = ResultResource
	
    def get_import_form(self):
        return RaceImportForm

    def get_confirm_import_form(self):
        return ConfirmRaceImportForm

    def get_resource_kwargs(self, request, *args, **kwargs):
        rk = super().get_resource_kwargs(request, *args, **kwargs)
        rk['request'] = request
        return rk

    def get_form_kwargs(self, form, *args, **kwargs):
        # pass on `author` to the kwargs for the custom confirm form
        if isinstance(form, RaceImportForm):
            if form.is_valid():
                race = form.cleaned_data['race']
                kwargs.update({'race': race.id})
        return kwargs

    

admin.site.register(Result, CustomResultAdmin)



class AthleteResource(resources.ModelResource):
    """ Example CSV:
    
name,club
Joe Morrow,OUCCC
Tom Wood,OUCCC

"""

    club = Field(
        column_name='club',
        attribute='club',
        widget=ForeignKeyWidget(Club, 'name'))


    # Fill id column
    def before_import(self, dataset, using_transactions, dry_run, **kwargs):
        print("Before import")
        dataset.insert_col(0, col=["",]*dataset.height, header="id")

    def before_import_row(self, row, row_number=None, **kwargs):
        print("Before row import")
        if not "power_of_10"  in row.keys() or row["power_of_10"] == "":

            name = None
            club = None
            if "club" in row.keys():
                club = row["club"]
            if "name" in row.keys():
                name = row["name"]

            if name:
                row["power_of_10"] = lookup_po10(name, club)

        print(row)

    def get_instance(self, instance_loader, row):
        return False

    class Meta:
        # fields
        model=Athlete
        fields = ('name', 'power_of_10', 'club', )
        # import_id_fields = ('name',)

class AthleteAdmin(ImportExportModelAdmin):
    resource_class = AthleteResource

admin.site.register(Athlete, AthleteAdmin)


class ResultInline(admin.TabularInline):
    model = Result

class RaceAdmin(admin.ModelAdmin):
    # list_display = ['title', 'status']
    # ordering = ['title']
    actions = ["compute_dividends", "distribute_dividends", "get_results_from_url"]

    inlines = [
        ResultInline,
    ]

    def get_results_from_url(self, request, queryset):
        # Collect errors and successes
        errors = []
        successes = []
        warnings = []
        for race in queryset:
            
            if not race.results_link:
                errors.append("No results link for race: {}".format(race))
                continue

            
            num_imported = 0

            #https://www.thepowerof10.info/results/results.aspx?meetingid=252978&event=9.15KXC&venue=Milton+Keynes&date=10-Nov-18
            #https://data.opentrack.run/x/2019/GBR/varsityxc/event/3/1/1/
            try:
                if 'powerof10.info' in race.results_link:
                    results = load_po10_results(race.results_link)
                # elif 'opentrack.run' in race.results_link:
                #     results = load_opentrack_results(race.results_link)
                else:
                    errors.append("{}: Don't know how to import from url: {}".format(race, race.results_link))
                    continue

            except XChangeException as e:
                        errors.append("{}: Error importing race: {} - {}".format(race, e.title, e.desc))

            imported_names = []
            skipped_names = []

            for r in results:
                try:
                    athlete = Athlete.objects.get(name=r.name)
                except Athlete.DoesNotExist:
                    continue

                # If athlete already has result, skip
                exists = Result.objects.all().filter(Q(race=race) & Q(athlete=athlete))
                if len(exists) > 0:
                    skipped_names.append(r.name)
                    continue

                new_result = Result(race=race, athlete=athlete, position=r.pos, time=r.time)
                new_result.save()
                num_imported = num_imported + 1
                imported_names.append(r.name)

            # Also do num competitors
            race.num_competitors = len(results)
            race.save()

            successes.append("{}: Imported {} results and updated number of competitors={}. Athletes imported: {}".format(race, num_imported, len(results), ', '.join(imported_names)))

            if skipped_names:
                warnings.append("{}: The following athletes already have results so were skipped: {}".format(race, ', '.join(skipped_names)))
            

                
        if errors:
            for e in errors:
                self.message_user(request, e , messages.ERROR)

        if successes:
            for s in successes:
                self.message_user(request, s , messages.SUCCESS)

        for w in warnings:
            self.message_user(request, w , messages.WARNING)

    get_results_from_url.short_description = "Get results from URL (Supported sites: Powerof10)"

    def compute_dividends(self, request, queryset):
        # queryset.update(status='p')
        for race in queryset:
            error = race.compute_dividends()

            if error:
                self.message_user(request, error, messages.ERROR)
                return

        self.message_user(request, "Dividends computed", messages.SUCCESS)

    def distribute_dividends(self, request, queryset):
        # queryset.update(status='p')
        for race in queryset:
            error = race.distribute_dividends()

            if error:
                self.message_user(request, error, messages.ERROR)
                return

        self.message_user(
            request, "Dividends distributed to share holders", messages.SUCCESS
        )


admin.site.register(Race, RaceAdmin)


class LotInline(admin.TabularInline):
    model = Lot

class BidInline(admin.TabularInline):
    model = Bid

class LotAdmin(admin.ModelAdmin):
    inlines = [BidInline, ]

admin.site.register(Lot, LotAdmin)
admin.site.register(Bid)

class AuctionAdmin(admin.ModelAdmin):
    # list_display = ['title', 'status']
    # ordering = ['title']
    actions = ["settle_bids"]

    inlines = [
        LotInline,
    ]

    def settle_bids(self, request, queryset):
        bank = cowley_club_bank()
        for auction in queryset:
            error = None

            if auction.end_date > current_time():
                error = "Auction hasn't finished yet: {}".format(auction.name)

            else:
                # Process bids from highest to smallest price per volume
                bids = Bid.objects.all().filter(lot__auction=auction,status=Bid.PENDING).order_by('-price_per_volume')

                for bid in bids:

                    # Skip bids for no shares
                    if bid.volume == 0:
                        continue
                    
                    
                    try:
                        # try making and executing trade
                        # if there are any issues e.g. insufficient shares, funds, then trade will
                        # fail and we ignore the exception then move on to the next one
                        total_price = bid.price_per_volume * bid.volume
                        trade = Trade.make_share_trade(bid.lot.athlete, bid.volume, creator=bid.bidder, 
                                            price=total_price, seller=bank, buyer=bid.bidder)

                        trade.accept_trade(action_by=bank)

                        bid.status=Bid.ACCEPTED
                        bid.save()
                        print("Accepted bid: {}".format(bid))
                    except XChangeException as e:
                        bid.status=Bid.REJECTED
                        bid.save()
                        print("Could not accept bid: {}".format(bid))
                        print(e)
                        

            if error:
                self.message_user(request, error, messages.ERROR)
                return

        self.message_user(request, "Bids settled", messages.SUCCESS)



admin.site.register(Auction, AuctionAdmin)