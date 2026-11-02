from django.urls import path

from bench.views import home


app_name = "bench"

urlpatterns = [
    path("", home.bench_home, name="home"),
]
