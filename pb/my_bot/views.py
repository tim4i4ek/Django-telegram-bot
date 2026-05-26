from rest_framework import generics, status
from rest_framework.response import Response
from .models import WorkingDay, Work, Appointment
from .serializers import WorkingDaySerializer, WorkSerializer, AppointmentCreateSerializer


class ScheduleListView(generics.ListAPIView):
    """Повертає список днів, відсортованих за порядком (від понеділка), разом із годинами."""
    queryset = WorkingDay.objects.all().order_by('day_index')
    serializer_class = WorkingDaySerializer


class ServiceListView(generics.ListAPIView):
    """Повертає список усіх послуг, які доступні для запису."""
    queryset = Work.objects.filter(available=True)  # Показуємо лише активні послуги
    serializer_class = WorkSerializer


class AppointmentCreateView(generics.CreateAPIView):
    """Обробляє створення нового запису через Telegram-бота з повною валідацією."""
    queryset = Appointment.objects.all()
    # Використовуємо саме CreateSerializer, де прописана наша валідація годин
    serializer_class = AppointmentCreateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            self.perform_create(serializer)
            return Response(
                {"message": "Запис успішно створено!"},
                status=status.HTTP_201_CREATED
            )

        # Якщо валідація не пройшла (час зайнятий або неробочий), бот отримає текст помилки
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)