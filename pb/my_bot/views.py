from rest_framework import generics, status
from rest_framework.response import Response
from .models import WorkingDay, Work, Appointment
from .serializers import WorkingDaySerializer, WorkSerializer, AppointmentCreateSerializer


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
            self.perform_create(serializer)
            return Response(
                {"message": "Запис успішно створено!"},
                status=status.HTTP_201_CREATED
            )


        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)