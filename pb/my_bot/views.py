from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import WorkingDay, Work, Appointment
from .serializers import WorkingDaySerializer, WorkSerializer, AppointmentCreateSerializer, AppointmentSerializer
from datetime import date

class ScheduleListView(generics.ListAPIView):
    queryset = WorkingDay.objects.all().order_by('day_index')
    serializer_class = WorkingDaySerializer


class ServiceListView(generics.ListAPIView):
    queryset = Work.objects.filter(available=True)
    serializer_class = WorkSerializer


class AppointmentCreateView(generics.CreateAPIView):
    queryset = Appointment.objects.all()
    serializer_class = AppointmentCreateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            existing_ids = set(Appointment.objects.values_list('id', flat=True))
            target_id = 1
            while target_id in existing_ids:
                target_id += 1
            appointment = serializer.save(id=target_id)
            return Response(
                {
                    "message": "Запис успішно створено!",
                    "id": appointment.id
                },
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AppointmentDeleteView(generics.DestroyAPIView):
    queryset = Appointment.objects.all()
    serializer_class = AppointmentSerializer

class ClientAppointmentListView(generics.ListAPIView):
    serializer_class = AppointmentSerializer

    def get_queryset(self):
        nickname = self.kwargs['nickname'].replace('@', '').strip()
        return Appointment.objects.filter(client_nickname__iexact=f"@{nickname}", date__gte=date.today()).order_by('date', 'time_slot')


class AppointmentApproveView(APIView):
    def post(self, request, pk):
        try:
            appointment = Appointment.objects.get(pk=pk)
            appointment.is_approved = True
            appointment.save()
            print(f"[STAFF API] Запис №{pk} успішно підтверджено працівником.")
            return Response({"message": "Запис успішно підтверджено!"}, status=status.HTTP_200_OK)
        except Appointment.DoesNotExist:
            print(f"[STAFF API ERROR] Спроба підтвердити неіснуючий запис №{pk}.")
            return Response({"error": "Запис не знайдено."}, status=status.HTTP_404_NOT_FOUND)