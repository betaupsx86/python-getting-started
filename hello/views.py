from decimal import Decimal
from locale import currency
from django.shortcuts import render
from django.http import HttpResponse
from django.http.response import JsonResponse


from rest_framework.parsers import JSONParser 
from rest_framework import status
from rest_framework.decorators import api_view

from .models import Greeting, PaymentIntent, ProdigiOrder
from .serializers import PaymentIntentSerializer
import json
import stripe

import requests
import os

from functools import reduce
   
import logging

from django.core import serializers
logger = logging.getLogger(__name__)

prodigi_api_key = 'test_97a1e474-0b3e-4ee9-9fb7-3557ff768607'
SERVICE_CHARGE = Decimal(1.05)

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
        key = stripe.EphemeralKey.create(
            customer = customer.id,
            stripe_version = request.POST.get("api_version")
            )
        return JsonResponse(key)
    except stripe.error.StripeError as e:
        # status 402
        # return log_info("Error creating ephemeral key: #{e.message}")
        raise e

def prodigi_quote(shippingMethod = "Budget", destinationCountryCode = "US", currencyCode="USD", items = list()):
    stripe.api_key = os.environ.get('STRIPE_TEST_SECRET_KEY')

    url = 'https://api.sandbox.prodigi.com/v4.0/quotes'
    headers = {
        'X-API-Key' : prodigi_api_key,
        'Content-type': 'application/json',
        }
    payload = {
        "shippingMethod": shippingMethod,
        "destinationCountryCode": destinationCountryCode,
        "currencyCode":currencyCode,
        "items": items,
    }

    quote_response = requests.post(url,headers=headers,data=json.dumps(payload))
    return quote_response


@api_view(['POST'])
def get_quote(request):
    stripe.api_key = os.environ.get('STRIPE_TEST_SECRET_KEY')
    customer = authenticate(request)
    try:
        url = 'https://api.sandbox.prodigi.com/v4.0/quotes'
        headers = {
            'X-API-Key' : prodigi_api_key,
            'Content-type': 'application/json',
            }
        payload = request.data
        response = requests.post(url,data=json.dumps(payload),headers=headers)
        return JsonResponse(response.json(), safe=False)
    except stripe.error.StripeError as e:
        raise e

@api_view(['POST'])
def get_quotes(request):
    stripe.api_key = os.environ.get('STRIPE_TEST_SECRET_KEY')
    customer = authenticate(request)
    try:
        url = 'https://api.sandbox.prodigi.com/v4.0/quotes'
        headers = {
            'X-API-Key' : prodigi_api_key,
            'Content-type': 'application/json',
            }
        quotes = list()
        for quote in request.data:
            quote_response = requests.post(url,data=json.dumps(quote),headers=headers)
            quotes.append(quote_response.json())

        return JsonResponse(quotes, safe=False)
    except stripe.error.StripeError as e:
        raise e

def prodigi_order(merchantReference=None, callbackUrl=None, idempotencyKey=None, shippingMethod = "Budget", recipient = dict, items = list()):
    stripe.api_key = os.environ.get('STRIPE_TEST_SECRET_KEY')

    url = 'https://api.sandbox.prodigi.com/v4.0/Orders'
    headers = {
        'X-API-Key' : prodigi_api_key,
        'Content-type': 'application/json',
        }
    payload = {
        "merchantReference": merchantReference,
        "callbackUrl": callbackUrl,
        "idempotencyKey": idempotencyKey,
        "shippingMethod": shippingMethod,
        "recipient": recipient,
        "items": items,
    }

    order_response = requests.post(url,headers=headers,data=json.dumps(payload))
    return order_response

def create_trial_prodigi_order():
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
    return response

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
    # amount = calculate_price(payment_intent_request["products"], payment_intent_request["shippingMethod"])
    # do_prodigi_request(payment_intent_request)
    def get_prodigi_quote(payment_intent_request):
        prodigi_items = list()
        sku_to_id = dict()
        stripe_subtotal = Decimal(0.0)
        for product in payment_intent_request["products"]:
            # We can use the stripe record of the product to crossreference and check prices
            stripe_product = stripe.Product.retrieve(product["id"])
            stripe_unit_price = price_lookup(product["id"])
            stripe_subtotal += Decimal(stripe_unit_price * product["quantity"])
            sku_to_id[stripe_product["metadata"]["sku"]] = stripe_product["id"]
            prodigi_attributes = dict(filter(lambda x: x[0] != "scale", product["attributes"].items()))
            prodigi_items.append({
                "sku":stripe_product["metadata"]["sku"],
                "copies": product["quantity"],
                "attributes": prodigi_attributes,
                "assets": [{"printArea": "default"}]               
            })        

        country_currency = currency_for_country(payment_intent_request["country"])
        quote_response = prodigi_quote(
            shippingMethod = payment_intent_request.get("shipmentMethod"),
            destinationCountryCode = payment_intent_request["shippingInformation"]["address"]["country"],
            currencyCode = country_currency,
            items = prodigi_items
        )

        quotes = quote_response.json()
        # Verify that everything is correct with the quote ie: Is not less than what we are charging the customer
        assert(quotes["outcome"] == "Created")
        quote = quotes["quotes"][0]
        assert(quote["costSummary"]["items"]["currency"].lower() == country_currency)
        items_cost = Decimal(quote["costSummary"]["items"]["amount"]) * 100
        assert(quote["costSummary"]["shipping"]["currency"].lower() == country_currency)
        shipping_cost = Decimal(quote["costSummary"]["shipping"]["amount"]) * 100

        if items_cost > stripe_subtotal:
            for item in quote["items"]:
                product_id = sku_to_id.get(item["sku"], None)
                unit_amount = int(Decimal(item["unitCost"]["amount"]) * 100)      
                currency = item["unitCost"]["currency"].lower()
                if product_id:         
                    update_price(product_id, unit_amount, currency, True)
                    sku_to_id.pop(item["sku"])                    

        # We can return and adjust item prices here depending on demand etc
        total_cost = (shipping_cost + items_cost)
        return prodigi_items, total_cost

    prodigi_items, prodigi_quote_total = get_prodigi_quote(payment_intent_request)     
    try:
        payment_intent = stripe.PaymentIntent.create(
        amount= int(prodigi_quote_total * SERVICE_CHARGE),
        currency=currency_for_country(payment_intent_request["country"].lower()),
        customer=payment_intent_request.get("customerId", customer.id),
        description="Example PaymentIntent",
        capture_method="manual" if os.environ.get('CAPTURE_METHOD') == "manual" else "automatic",
        payment_method_types= supported_payment_methods if supported_payment_methods else payment_methods_for_country(payment_intent_request["country"]),
        metadata={
            "shippingMethod": payment_intent_request["shippingMethod"],
            "shippingInformation": json.dumps(payment_intent_request["shippingInformation"]),
            "products": json.dumps(payment_intent_request["products"]),
            "prodigi_items": json.dumps(prodigi_items) # Should have the same order as products list``
            },
        )

        logger.warning("PaymentIntent successfully created: id {}, customer {}".format(payment_intent.id, payment_intent.customer))
        return JsonResponse(
            {
                "intent" : payment_intent.id,
                "secret" : payment_intent.client_secret,
                "status" : payment_intent.status,
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

# This is your Stripe CLI webhook secret for testing your endpoint locally.
endpoint_secret = 'whsec_YDgUbLJPhZ5ZWAaaSqWThyOdirHvcdTZ'

@api_view(['POST'])
def stripe_webhook(request):
    payload = request.body
    event = None

    try:
        event = stripe.Event.construct_from(
        json.loads(payload), stripe.api_key
        )
    except ValueError as e:
        # Invalid payload
        return HttpResponse(status=400)

    logger.warning("============EVENTS=================")
    # Handle the event
    if event.type == 'payment_intent.succeeded':
        logger.warning("============PAYMENT INTENT SUCCEEDED=================")
        payment_intent = event.data.object # contains a stripe.PaymentIntent
        # Then define and call a method to handle the successful payment intent.
        # handle_payment_intent_succeeded(payment_intent)
        logger.warning("============PAYMENT INTENT=================")
        logger.warning(payment_intent)
        logger.warning("============PRODIGI ORDER=================")

            # "shippingMethod": payment_intent_request["shippingMethod"],
            # "shippingInformation": json.dumps(payment_intent_request["shippingInformation"]),
            # "products": json.dumps(payment_intent_request["products"]),
            # "prodigi_items": json.dumps(prodigi_items) # Should have the same order as products list``


        order_response = create_trial_prodigi_order()

        
        logger.warning(order_response.content)

        logger.warning("============PRODIGI ORDER DESERIALIZE=================")
        d = serializers.serialize('json', ProdigiOrder.objects.all()) # serialize all the objects in Order model
        for obj in serializers.deserialize('json', d):
            logger.warning(obj.object) ## return the django model class object 

    elif event.type == 'payment_method.attached':
        logger.warning("============PAYMENT METHOD SUCCEEDED=================")
        payment_method = event.data.object # contains a stripe.PaymentMethod
        # Then define and call a method to handle the successful attachment of a PaymentMethod.
        # handle_payment_method_attached(payment_method)
    # ... handle other event types
    else:
        print('Unhandled event type {}'.format(event.type))

    return HttpResponse(status=200)


@api_view(['POST'])
def prodigi_webhook(request):
    logger.warning("============EVENTS PRODIGI=================")
    prodigi_event  = json.loads(request.body)
    logger.warning(prodigi_event)

    return HttpResponse(status=200)


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

def create_price(product, unit_amount, currency):  
    return stripe.Price.create(currency = currency, unit_amount = unit_amount, product = product)

def update_price(product, unit_amount, currency, create_if_missing = False):    
    prices = stripe.Price.list(product=product)
    for price in prices:
        if price["currency"] == currency:
            new_price = stripe.Price.create(currency = currency, unit_amount = unit_amount, product = product)
            stripe.Price.modify(price["id"], active=False, metadata={"substitute": new_price["id"]})
            return new_price

    if create_if_missing:
        return create_price(product, unit_amount, currency)

    return None

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
