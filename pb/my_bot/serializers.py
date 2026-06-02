from .models import WorkingHour, Work, Appointment, WorkingDay
from rest_framework import serializers
from datetime import date as datetime_date
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
        fields = ['id', 'client_name', 'date', 'time_slot', 'proposition', 'price', 'client_nickname']



class AppointmentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = ['client_name', 'date', 'time_slot', 'proposition', 'price', 'client_nickname', 'is_approved']
        read_only_fields = ('is_approved',)

    def validate(self, data):

        client_nickname = data.get('client_nickname')
        if client_nickname and client_nickname != "Приховано":

            active_appointments_count = Appointment.objects.filter(
                client_nickname=client_nickname,
                date__gte=datetime_date.today()
            ).count()

            if active_appointments_count >= 3:
                raise serializers.ValidationError(
                    "У вас уже є 3 активні записи! Ви не можете створити нову, поки не мине або не скасується одна з існуючих."
                )


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


