from django.db import models

# Create your models here.
class Greeting(models.Model):
    when = models.DateTimeField("date created", auto_now_add=True)

class PaymentIntent(models.Model):
    title = models.CharField(max_length=70, blank=False, default="default_title")
    description = models.CharField(max_length=200,blank=False, default="default_description")
