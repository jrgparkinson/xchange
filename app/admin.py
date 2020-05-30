from django.contrib import admin
from .models import *

admin.site.register(Investor)

admin.site.register(Event)


admin.site.register(Athlete)
admin.site.register(Team)

from django.contrib import messages


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
