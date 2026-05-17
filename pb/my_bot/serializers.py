from rest_framework import serializers
from .models import WorkingDay, WorkingHour, Work

class WorkingHourSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkingHour
        fields = ['all_hours']

class WorkSerializer(serializers.ModelSerializer):
    class Meta:

        model = Work
        fields = ['proposition', 'price', 'available']

class WorkingDaySerializer(serializers.ModelSerializer):

    hours = WorkingHourSerializer(many=True, read_only=True)

    class Meta:
        model = WorkingDay
        fields = ['day_index', 'is_working', 'hours']

from .models import Appointment

class AppointmentSerializer(serializers.ModelSerializer):
    class Meta:

        unique_together = ('date', 'time_slot')

        model = Appointment
        fields = ['client_name', 'date', 'time_slot','proposition', 'price']


from rest_framework import serializers
from .models import Appointment, WorkingDay


class AppointmentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = ['client_name', 'date', 'time_slot', 'proposition', 'price','client_nickname', 'is_approved']
        read_only_fields = ('client_nickname', 'is_approved')
    def validate(self, data):

        weekday = data['date'].weekday()
        working_day = WorkingDay.objects.filter(day_index=weekday, is_working=True).first()

        if not working_day:
            raise serializers.ValidationError("Вибачте, у цей день я не працюю.")


        hour_exists = working_day.hours.filter(hour=data['time_slot']).exists()
        if not hour_exists:
            raise serializers.ValidationError("У цей час я не приймаю.")

        already_booked = Appointment.objects.filter(date=data['date'], time_slot=data['time_slot']).exists()
        if already_booked:
            raise serializers.ValidationError("Цей час уже зайнятий.")

        return data


