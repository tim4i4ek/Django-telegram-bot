from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from datetime import datetime, timedelta
import PIL

class WorkingDay(models.Model):
    DAYS = [
        (0, 'Понеділок'), (1, 'Вівторок'), (2, 'Середа'),
        (3, 'Четвер'), (4, 'П’ятниця'), (5, 'Субота'), (6, 'Неділя'),
    ]
    day_index = models.IntegerField("День тижня (0-6)", choices=DAYS, unique=True)
    is_working = models.BooleanField("Чи робочий?", default=True)

    def __str__(self):
        return dict(self.DAYS).get(self.day_index, "Невідомо")


    def get_slots(self):

        config = self.hours.first()
        if not config or not self.is_working:
            return []

        slots = []
        current = config.hour_start_work
        while current < config.hour_end_work:
            slots.append(current)
            current += 1
        return slots


class WorkingHour(models.Model):
    INTERVAL_CHOICES = [
        (10, '10 хв'), (15, '15 хв'), (20, '20 хв'),
        (30, '30 хв'), (45, '45 хв'), (60, '60 хв'),
    ]

    working_day = models.OneToOneField(WorkingDay, on_delete=models.CASCADE, related_name='hours')
    hour_start_work = models.IntegerField("Початок (0-23)", default=9,
                                          validators=[MinValueValidator(0), MaxValueValidator(23)])
    hour_end_work = models.IntegerField("Кінець (0-23)", default=18,
                                        validators=[MinValueValidator(0), MaxValueValidator(23)])
    interval = models.IntegerField("Інтервал", choices=INTERVAL_CHOICES, default=60)

    def __str__(self):
        return f"{self.hour_start_work}:00 - {self.hour_end_work}:00 (крок {self.interval}м)"


class Work(models.Model):
    proposition = models.CharField("Назва послуги", max_length=100)
    price = models.DecimalField("Ціна", max_digits=10, decimal_places=2)
    available = models.BooleanField("Доступно", default=True)
    image = models.ImageField("фото послуги", upload_to='services/', null=True, blank=True)
    def __str__(self):
        return f"{self.proposition} ({self.price} грн)"


class Appointment(models.Model):
    client_name = models.CharField(max_length=100)
    date = models.DateField()
    time_slot = models.IntegerField()
    proposition = models.ForeignKey(Work, on_delete=models.CASCADE, related_name='appointments')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    client_nickname = models.CharField(max_length=100)
    is_approved = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.client_name} - {self.date} {self.time_slot}:00"