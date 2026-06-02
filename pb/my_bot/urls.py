from django.urls import path
from .views import ScheduleListView, ServiceListView, AppointmentCreateView, AppointmentDeleteView, ClientAppointmentListView, AppointmentApproveView

urlpatterns = [
    path('schedule/', ScheduleListView.as_view(), name='schedule-list'),
    path('services/', ServiceListView.as_view(), name='service-list'),
    path('book/', AppointmentCreateView.as_view(), name='book-appointment'),
    path('book/<int:pk>/delete/', AppointmentDeleteView.as_view(), name='delete-appointment'),
    path('client/appointments/<str:nickname>/', ClientAppointmentListView.as_view()),
    path('book/<int:pk>/approve/', AppointmentApproveView.as_view()),
]