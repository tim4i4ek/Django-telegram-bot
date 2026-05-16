from django.contrib import admin
from .models import WorkingDay, WorkingHour, Work, Appointment

from django.utils.safestring import mark_safe

@admin.register(Work)
class WorkAdmin(admin.ModelAdmin):
    list_display = ('proposition', 'price', 'get_image','available')

    def get_image(self, obj):
        if obj.image:
            return mark_safe(f'<img src="{obj.image.url}" width="50" height="50" />')
        return "Нема фото"
@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):

    list_display = ('client_name', 'date', 'time_slot', 'proposition', 'price')
    list_filter = ('date', 'proposition')

admin.site.register(WorkingDay)
admin.site.register(WorkingHour)