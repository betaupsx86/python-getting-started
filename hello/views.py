from django.shortcuts import render
from django.http import HttpResponse
from django.http.response import JsonResponse


from rest_framework.parsers import JSONParser 
from rest_framework import status
from rest_framework.decorators import api_view

from .models import Greeting, PaymentIntent
from .serializers import PaymentIntentSerializer
import json
import stripe

import requests
import os

from functools import reduce
   
import logging
logger = logging.getLogger(__name__)

prodigi_api_key = 'test_97a1e474-0b3e-4ee9-9fb7-3557ff768607'

def authenticate(request):
  # This code simulates "loading the Stripe customer for your current session".
  # Your own logic will likely look very different.
    if not request:
        return None
    customer_id = request.session.get("customer_id")
    if customer_id:
        try:
            return stripe.Customer.retrieve(customer_id)
        except stripe.error.InvalidRequestError as e:
            # rescue stripe.error.StripeError : e
            # status 402
            raise e
            # return log_info("Error creating ephemeral key: #{e.message}")
            # raise Http404("Poll does not exist")
    else:
        default_customer_id = os.environ.get('DEFAULT_CUSTOMER_ID')
        if default_customer_id:
            try:
                customer = stripe.Customer.retrieve(customer_id)
                request.session["customer_id"] = customer.id
                return customer
            except stripe.error.InvalidRequestError as e:
                # rescue stripe.error.StripeError : e
                # status 402
                raise e
                # return log_info("Error creating ephemeral key: #{e.message}")
                # raise Http404("Poll does not exist")
        else:
            try:                
                customer = create_customer()
                request.session["customer_id"] = customer.id
                if (stripe.api_key.startswith('sk_test_')):
                    # only attach test cards in testmode
                    attach_customer_test_cards(customer.id)
                return customer
            except stripe.error.InvalidRequestError as e:
                # rescue stripe.error.StripeError : e
                # status 402
                raise e
                # return log_info("Error creating ephemeral key: #{e.message}")
                # raise Http404("Poll does not exist")

def create_customer():
    return stripe.Customer.create(
        description = 'mobile SDK example customer',
        metadata = {
            # Add our application's customer id for this Customer, so it'll be easier to look up
            "my_customer_id" : '72F8C533-FCD5-47A6-A45B-3956CA8C792D',
        },
    )

def attach_customer_test_cards(customer_id):
  # Attach some test cards to the customer for testing convenience.
  # See https://stripe.com/docs/payments/3d-secure#three-ds-cards
  # and https://stripe.com/docs/mobile/android/authentication#testing
    # cc_numbers = ['4000000000003220', '4000000000003063', '4000000000003238', '4000000000003246', '4000000000003253', '4242424242424242']
    cc_numbers = ['4000000000003253','4242424242424242']
    for cc_number in cc_numbers:
        payment_method = stripe.PaymentMethod.create(
            type = "card",
            card = {
                "number": cc_number,
                "exp_month": 8,
                "exp_year": 2022,
                "cvc": '123',
            },
        )

        stripe.PaymentMethod.attach(
            payment_method.id,
            customer = customer_id
        )


@api_view(['POST'])
def ephemeral_keys(request):
    stripe.api_key = os.environ.get('STRIPE_TEST_SECRET_KEY')
    customer = authenticate(request)
    try:
        # ephemeral_keys_request = JSONParser().parse(request)
        # logger.error(ephemeral_keys_request)
        # key = stripe.EphemeralKey.create(
        #     {"customer": customer.id},
        #     {"stripe_version": ephemeral_keys_request["api_version"]}
        #     )
        key = stripe.EphemeralKey.create(
            customer = customer.id,
            stripe_version = request.POST.get("api_version")
            )
        return JsonResponse(key)
    except stripe.error.StripeError as e:
        # status 402
        # return log_info("Error creating ephemeral key: #{e.message}")
        raise e

def prodigi_quote(quote_request):
    url = 'https://api.sandbox.prodigi.com/v4.0/quotes'
    headers = {
        'X-API-Key' : prodigi_api_key,
        'Content-type': 'application/json',
        # 'Accept': 'text/plain'
        }
    payload = {
        "shippingMethod": quote_request.get("shippingMethod"),
        "destinationCountryCode": quote_request.get("shippingDestination"),
        "currencyCode":quote_request.get("currency"),
        "items": [
            {
                "sku": product.get("sku"),
                "copies": product.get("copies"),
                "attributes": product.get("metadata"),
                "assets" : [
                    { "printArea" : "default" }
                ]
            }           
            for product in quote_request.get("products")
        ]
    }
    logger.warning(payload)

    response = requests.post(url,data=json.dumps(payload),headers=headers)
    quote = response.json()
    logger.warning(quote)
    logger.warning(response)
    return quote
    # quote = JSONParser().parse(response)
    # logger.warning(quote)
    # return quote


@api_view(['POST'])
def get_quote(request):
    stripe.api_key = os.environ.get('STRIPE_TEST_SECRET_KEY')
    customer = authenticate(request)
    quote_request = JSONParser().parse(request)

    try:
        quote = prodigi_quote(quote_request)
        return JsonResponse(quote, safe=False)
        # return quote
    except stripe.error.StripeError as e:
        raise e

def do_prodigi_request(payment_intent_request):
    url = 'https://api.sandbox.prodigi.com/v4.0/Orders'

    headers = {
        'X-API-Key' : prodigi_api_key,
        'Content-type': 'application/json',
        # 'Accept': 'text/plain'
        }
    payload = {
        "shippingMethod": "Budget",
        "recipient": {
            "address": {
                "line1": "14 test place",
                "line2": "test",
                "postalOrZipCode": "12345",
                "countryCode": "US",
                "townOrCity": "somewhere",
                "stateOrCounty": "somewhereelse"
            },
            "name": "John Testman",
            "email": "jtestman@prodigi.com"
        },
        "items": [
            {
                "sku": "GLOBAL-FAP-16x24",
                "copies": 1,
                "sizing": "fillPrintArea",
                "assets": [
                    {
                        "printArea": "default",
                        "url": "https://your-image-url/image.png"
                    }
                ]
            }
        ]
    }
    response = requests.post(url,data=json.dumps(payload),headers=headers)
    order = JSONParser().parse(request)
    logger.warning(order)

@api_view(['POST'])
def create_payment_intent(request):
    stripe.api_key = os.environ.get('STRIPE_TEST_SECRET_KEY')
    customer = authenticate(request)
    payment_intent_request = JSONParser().parse(request)

    # if request.content_type and request.content_type == 'application/json':
    #     payment_intent_request = JSONParser().parse(request)
    # else:
    #     payment_intent_request = request.POST 

    supported_payment_methods = payment_intent_request.get("supported_payment_methods").split(",") if payment_intent_request.get("supported_payment_methods") else None

    # Calculate how much to charge the customer
    logger.error(payment_intent_request.keys())
    amount = calculate_price(payment_intent_request["products"], payment_intent_request["shippingMethod"])
    do_prodigi_request(payment_intent_request)

    try:
        payment_intent = stripe.PaymentIntent.create(
        amount=amount,
        currency=currency_for_country(payment_intent_request["country"]),
        customer=payment_intent_request.get("customer_id", customer.id),
        description="Example PaymentIntent",
        capture_method="manual" if os.environ.get('CAPTURE_METHOD') == "manual" else "automatic",
        payment_method_types= supported_payment_methods if supported_payment_methods else payment_methods_for_country(payment_intent_request["country"]),
        metadata={"order_id" : '5278735C-1F40-407D-933A-286E463E72D8'}.update(payment_intent_request.get("metadata",{})),
        )

        logger.warning("PaymentIntent successfully created: #{payment_intent.id}")
        return JsonResponse(
            {
                "intent" : payment_intent.id,
                "secret" : payment_intent.client_secret,
                "status" : payment_intent.status
                },
            safe=False
            )
    except stripe.error.StripeError as e:
        raise e

# @api_view(['POST'])
# def create_payment_intent(request):
#     payment_intent_request = JSONParser().parse(request)

#     if payment_intent_request and payment_intent_request["id"] == "1":
#         test_payment_intent = PaymentIntent(title="test_1", description="description_1")
#     else:
#         test_payment_intent = PaymentIntent(title="test", description="description")
#     tutorials_serializer = PaymentIntentSerializer(test_payment_intent)
#     return JsonResponse(tutorials_serializer.data, safe=False)

# def index(request):
#     r = requests.get('http://httpbin.org/status/418')
#     print(r.text)
#     return HttpResponse('<pre>' + r.text + '</pre>')

def index(request):
    times = int(os.environ.get('TIMES',3))
    return HttpResponse('Hello! ' * times)


def db(request):

    greeting = Greeting()
    greeting.save()

    greetings = Greeting.objects.all()

    return render(request, "db.html", {"greetings": greetings})


def generate_payment_response(payment_intent):
  # Note that if your API version is before 2019-02-11, 'requires_action'
  # appears as 'requires_source_action'.
    if payment_intent.status == 'requires_action':
        # Tell the client to handle the action
        return JsonResponse(
        {
            "requires_action" : True,
            "secret" : payment_intent.client_secret,
            },
        safe=False
        )
    elif payment_intent.status == 'succeeded' or (payment_intent.status == 'requires_capture' and os.environ.get('CAPTURE_METHOD') == "manual"):
        # The payment didn’t need any additional actions and is completed!
        # Handle post-payment fulfillment
        return JsonResponse(
        {
            "success" : True,
            },
        safe=False
        )
    else:
        return HttpResponse("Invalid PaymentIntent status", status=500)



# ===== Helpers

# Our example apps sell emoji apparel; this hash lets us calculate the total amount to charge.
EMOJI_STORE = {
  "👕" : 2000,
  "👖" : 4000,
  "👗" : 3000,
  "👞" : 700,
  "👟" : 600,
  "👠" : 1000,
  "👡" : 2000,
  "👢" : 2500,
  "👒" : 800,
  "👙" : 3000,
  "💄" : 2000,
  "🎩" : 5000,
  "👛" : 5500,
  "👜" : 6000,
  "🕶" : 2000,
  "👚" : 2500,
}

def price_lookup(product):

    prices = stripe.Price.list(limit=3, product=product)
    price = prices.data[0]

    logger.warning(price)
    if price is None:
        raise BaseException("Can't find price for %s (%s)" % [product, product.ord.to_s(16)])
    return price["unit_amount"]

SHIPPING_COST = {
    "ups_ground":599,
    "fedex":599,
    "fedex_world":2099,
    "ups_worldwide":1099,
}
def calculate_price(products, shipping):
    subtotal = 0
    if products:
        for product in products:           
            subtotal += price_lookup(product)

    shipping_cost = 0
    if shipping:
        shipping_cost = SHIPPING_COST.get(shipping)

    tax = 0.09
    return int(subtotal * (1 + tax) + shipping_cost)

COUNTRY_CURRENCY = {
    'us':'usd',
    'mx':'mxn',
    'my':'myr',
    'at':'eur',
    'be':'eur',
    'de':'eur',
    'es':'eur',
    'it':'eur',
    'nl':'eur',
    'pl':'eur',
    'au':'aud',
    'gb':'gbp',
    'in':'inr',
}
def currency_for_country(country):
    # Determine currency to use. Generally a store would charge different prices for
    # different countries, but for the sake of simplicity we'll charge X of the local currency.
    return COUNTRY_CURRENCY.get(country, 'usd')

COUNTRY_PAYMENT_METHODS = {
    'us':['card'],
    'mx':['card', 'oxxo'],
    'my':['card', 'fpx', 'grabpay'],
    'at':['card', 'paypal', 'sofort', 'eps'],
    'be':['card', 'paypal', 'sofort', 'bancontact' ],
    'de':['card', 'paypal', 'sofort', 'giropay'],
    'es':['card', 'paypal', 'sofort'],
    'it':['card', 'paypal', 'sofort'],
    'nl':['card', 'ideal', 'sepa_debit', 'sofort' ],
    'pl':['card', 'paypal', 'p24' ],
    'au':['card', 'au_becs_debit'],
    'gb':['card', 'paypal', 'bacs_debit'],
    'in':['card', 'upi', 'netbanking' ],
    'sg':['card', 'alipay', 'grabpay']
}
def payment_methods_for_country(country):
    return COUNTRY_PAYMENT_METHODS.get(country, 'card')
