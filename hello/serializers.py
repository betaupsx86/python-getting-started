from rest_framework import serializers 
from .models import PaymentIntent
 
class PaymentIntentSerializer(serializers.ModelSerializer):

    class Meta:
        model = PaymentIntent
        fields = ('title', 'description')