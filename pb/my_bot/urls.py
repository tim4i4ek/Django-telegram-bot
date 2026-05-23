from django.urls import path
from .views import ScheduleListView, ServiceListView, AppointmentCreateView
from . import views

urlpatterns = [
    path('schedule/', views.WorkingDayListView.as_view(), name='schedule-list'),
    path('services/', ServiceListView.as_view(), name='service-list'),
    path('book/', AppointmentCreateView.as_view(), name='book-appointment'),
]