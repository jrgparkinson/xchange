from django.contrib import admin
from .models import *
from django.contrib import messages
from import_export.admin import ImportExportModelAdmin, ImportForm, ConfirmImportForm, ImportMixin
from import_export import resources
from import_export.fields import Field
from import_export.widgets import ForeignKeyWidget
from .po10 import lookup_po10
from django import forms

admin.site.register(Investor)
admin.site.register(Event)
admin.site.register(Team)

class ResultResource(resources.ModelResource):
    """ Example CSV import:

    athlete,position,time
Jamie Parkinson,10,00:30:00
    """

    athlete = Field(
        column_name='athlete',
        attribute='athlete',
        widget=ForeignKeyWidget(Athlete, 'name'))




    # Fill id column
    def before_import(self, dataset, using_transactions, dry_run, **kwargs):
        print("Before import")
        
        dataset.insert_col(0, col=["",]*dataset.height, header="id")
        print(dataset)

    def __init__(self, request=None):
        super()
        self.request = request

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

    def get_instance(self, instance_loader, row):
        return False

    class Meta:
        # fields
        model=Result
        # fields = ('athlete', 'race', 'position', 'time', )
        # import_id_fields = ('name',)

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

    team_last_year = Field(
        column_name='team_last_year',
        attribute='team_last_year',
        widget=ForeignKeyWidget(Team, 'name'))

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
        fields = ('name', 'power_of_10', 'club', 'team_last_year', )
        # import_id_fields = ('name',)

class AthleteAdmin(ImportExportModelAdmin):
    resource_class = AthleteResource

admin.site.register(Athlete, AthleteAdmin)


class ResultInline(admin.TabularInline):
    model = Result

class RaceAdmin(admin.ModelAdmin):
    # list_display = ['title', 'status']
    # ordering = ['title']
    actions = ["compute_dividends", "distribute_dividends"]

    inlines = [
        ResultInline,
    ]

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

    # make_published.short_description = "Mark selected stories as published"


admin.site.register(Race, RaceAdmin)
