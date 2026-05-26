from .models import WorkingHour, Work, Appointment, WorkingDay
from rest_framework import serializers

class WorkSerializer(serializers.ModelSerializer):
    class Meta:
        model = Work
        fields = ['proposition', 'price', 'available', 'id']

class WorkingDaySerializer(serializers.ModelSerializer):
    hours = serializers.SerializerMethodField()

    class Meta:
        model = WorkingDay
        fields = ['day_index', 'is_working', 'hours']

    def get_hours(self, obj):
        slots = obj.get_slots()
        return [{"hour": f"{slot:02d}:00"} for slot in slots]

class AppointmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = ['client_name', 'date', 'time_slot', 'proposition', 'price']


class AppointmentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = ['client_name', 'date', 'time_slot', 'proposition', 'price', 'client_nickname', 'is_approved']
        read_only_fields = ('client_nickname', 'is_approved')

    def validate(self, data):
        weekday = data['date'].weekday()

        working_day = WorkingDay.objects.filter(day_index=weekday, is_working=True).first()

        if not working_day:
            raise serializers.ValidationError("Вибачте, у цей день я не працюю.")


        allowed_slots = working_day.get_slots()

        if data['time_slot'] not in allowed_slots:
            raise serializers.ValidationError("У цей час я не приймаю.")

        already_booked = Appointment.objects.filter(date=data['date'], time_slot=data['time_slot']).exists()
        if already_booked:
            raise serializers.ValidationError("Цей час уже зайнятий.")

        return data