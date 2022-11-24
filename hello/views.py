from decimal import Decimal
from locale import currency
from unittest.mock import patch
from django.shortcuts import render
from django.http import HttpResponse
from django.http.response import JsonResponse

from rest_framework.parsers import JSONParser 
from rest_framework import status
from rest_framework.decorators import api_view

from cloudevents.http import from_http

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
    # stripe.api_key = os.environ.get('STRIPE_TEST_SECRET_KEY')

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

def prodigi_items_from_stripe_quote_request(quote_request):
    prodigi_items = list()
    sku_to_id = dict()
    id_to_unit_price = dict()
    stripe_subtotal = Decimal(0.0)

    # Call list API to fetch them all at the same time. Alternatively get one by one.
    stripe_products = stripe.Product.list(ids=[product["id"] for product in quote_request["items"]])
    id_to_stripe_products = {stripe_product["id"]:stripe_product for stripe_product in stripe_products}
    for item in quote_request["items"]:
        # We can use the stripe record of the product to crossreference and check prices
        stripe_product = id_to_stripe_products[item["id"]]
        stripe_unit_price = price_lookup(stripe_product["id"])
        stripe_subtotal += Decimal(stripe_unit_price * item["quantity"])

        id_to_unit_price[item["id"]] = stripe_unit_price
        sku_to_id[stripe_product["metadata"]["sku"]] = stripe_product["id"]

        prodigi_attributes = dict(filter(lambda x: x[0] != "scale" and x[0] != "assetUrl", item["attributes"].items()))
        prodigi_items.append({
            "sku":stripe_product["metadata"]["sku"],
            "copies": item["quantity"],
            "attributes": prodigi_attributes,
            "assets": [{"printArea": "default"}]               
        })

    return prodigi_items        


@api_view(['POST'])
def get_quote(request):
    stripe.api_key = os.environ.get('STRIPE_TEST_SECRET_KEY')
    customer = authenticate(request)
    try:
        quote_request = request.data
        if isinstance(quote_request["destinationCountryCode"], list):
            prodigi_items = prodigi_items_from_stripe_quote_request(quote_request)
            quotes = list()
            for destinationCountryCode in quote_request["destinationCountryCode"]:
                quote_response = prodigi_quote(
                    shippingMethod = quote_request.get("shipmentMethod", None),
                    destinationCountryCode = destinationCountryCode,
                    currencyCode = quote_request["currencyCode"],
                    items = prodigi_items
                ).json()
                quote_response["destinationCountryCode"] = destinationCountryCode
                quotes.append(quote_response)
            return JsonResponse(quotes, safe=False)             
        else:
            prodigi_items = prodigi_items_from_stripe_quote_request(quote_request)
            quote_response = prodigi_quote(
                    shippingMethod = quote_request.get("shipmentMethod", None),
                destinationCountryCode = quote_request["destinationCountryCode"],
                currencyCode = quote_request["currencyCode"],
                items = prodigi_items
            ).json()
            quote_response["destinationCountryCode"] = quote_request["destinationCountryCode"]
            return JsonResponse(quote_response, safe=False)
        
    except stripe.error.StripeError as e:
        raise e

@api_view(['POST'])
def get_quotes(request):
    stripe.api_key = os.environ.get('STRIPE_TEST_SECRET_KEY')
    customer = authenticate(request)
    try:
        quotes = list()
        for quote_request in request.data:
            prodigi_items = prodigi_items_from_stripe_quote_request(quote_request)
            quote_response = prodigi_quote(
                shippingMethod = quote_request["shipmentMethod"],
                destinationCountryCode = quote_request["destinationCountryCode"],
                currencyCode = quote_request["currencyCode"],
                items = prodigi_items
            ).json()
            quote_response["destinationCountryCode"] = quote_request["destinationCountryCode"]
            quotes.append(quote_response)

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
    logger.warning("============prodigi_order=================")
    logger.warning(order_response.json)
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

def get_prodigi_quote_for_payment_intent(payment_intent_request):
    prodigi_items = list()
    sku_to_id = dict()
    id_to_unit_price = dict()
    stripe_subtotal = Decimal(0.0)

    # Call list API to fetch them all at the same time. Alternatively get one by one.
    stripe_products = stripe.Product.list(ids=[product["id"] for product in payment_intent_request["products"]])
    id_to_stripe_products = {stripe_product["id"]:stripe_product for stripe_product in stripe_products}
    for product in payment_intent_request["products"]:
        # We can use the stripe record of the product to crossreference and check prices
        stripe_product = id_to_stripe_products[product["id"]]
        stripe_unit_price = price_lookup(stripe_product["id"])
        stripe_subtotal += Decimal(stripe_unit_price * product["quantity"])

        id_to_unit_price[product["id"]] = stripe_unit_price
        sku_to_id[stripe_product["metadata"]["sku"]] = stripe_product["id"]

        prodigi_attributes = dict(filter(lambda x: x[0] != "scale" and x[0] != "assetUrl", product["attributes"].items()))
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
    # Account for US Tax Code warning
    assert(quotes["outcome"] == "Created" or (quotes["outcome"] == "CreatedWithIssues" and quotes["issues"][0]["errorCode"]=="destinationCountryCode.UsSalesTaxWarning"))
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
                id_to_unit_price[product_id] = unit_amount         
                update_price(product_id, unit_amount, currency, True)
                sku_to_id.pop(item["sku"])                    

    # We can return and adjust item prices here depending on demand etc
    total_cost = (shipping_cost + items_cost)

    def stripe_to_prodigi_sizing(scale):
        if scale == "CENTER_CROP":
            return "fillPrintArea"
        elif scale == "FIT_CENTER":
            return "fitPrintArea"
        else:
            return "stretchToPrintArea"

    # Add the missing order data to prodigi items
    for prodigi_item, product in zip(prodigi_items, payment_intent_request["products"]):
        prodigi_item.update(
            {
                "merchantReference": product["id"],
                "sizing": stripe_to_prodigi_sizing(product["attributes"].get("scale", "CENTER_CROP")),
                # "recipientCost": {
                #     "amount": str(Decimal(id_to_unit_price[product["id"]]) / 100),
                #     "currency": country_currency
                # },
                "assets": [
                    {
                        "printArea": "default",
                        "url": product["attributes"].get("assetUrl",""),
                    }
                ]               
            }
        )

    return prodigi_items, total_cost


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

    # prodigi items will have the necessary data for the order. This will be used to create the order once paymente intent succeds:
    prodigi_items, prodigi_quote_total = get_prodigi_quote_for_payment_intent(payment_intent_request)
    metadata = {
        "shippingMethod": payment_intent_request["shippingMethod"],
        "recipient": json.dumps({
            "name": payment_intent_request["shippingInformation"]["name"],
            "address": stripe_to_prodigi_shipping_address(payment_intent_request["shippingInformation"]["address"]),
            "email": payment_intent_request["customerEmail"],
        }),
        "num_items": len(prodigi_items),
        "shippingInformation": json.dumps(payment_intent_request["shippingInformation"]),
    }
    metadata.update({"item_{}".format(idx):json.dumps(item) for idx, item in enumerate(prodigi_items)})
    logger.warning(metadata)


    try:
        payment_intent = stripe.PaymentIntent.create(
            amount= int(prodigi_quote_total * SERVICE_CHARGE),
            currency=currency_for_country(payment_intent_request["country"].lower()),
            customer=payment_intent_request.get("customerId", customer.id),
            description="Example PaymentIntent",
            capture_method="manual" if os.environ.get('CAPTURE_METHOD') == "manual" else "automatic",
            payment_method_types= supported_payment_methods if supported_payment_methods else payment_methods_for_country(payment_intent_request["country"].lower()),
            shipping = payment_intent_request["shippingInformation"],
            metadata=metadata,
            receipt_email=payment_intent_request["customerEmail"]
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

            # "shippingMethod": payment_intent_request["shippingMethod"],
            # "shippingInformation": json.dumps(payment_intent_request["shippingInformation"]),
            # "products": json.dumps(payment_intent_request["products"]),
            # "prodigi_items": json.dumps(prodigi_items) # Should have the same order as products list``
        def get_prodigi_order(payment_intent):
            order_response = prodigi_order(
                merchantReference=payment_intent["id"],
                callbackUrl=None,
                idempotencyKey=None,
                shippingMethod = payment_intent["metadata"]["shippingMethod"],
                recipient=json.loads(payment_intent["metadata"]["recipient"]),
                items = [json.loads(payment_intent["metadata"]["item_{}".format(idx)]) for idx in range(int(payment_intent["metadata"]["num_items"]))]
            )

            order = order_response.json()
            # assert(order["outcome"] == "Created")
            return order

        logger.warning("============PRODIGI ORDER=================")
        order = get_prodigi_order(payment_intent)
        logger.warning(order)

        logger.warning("============PRODIGI ORDER DESERIALIZE=================")
        d = serializers.serialize('json', ProdigiOrder.objects.all()) # serialize all the objects in Order model
        for obj in serializers.deserialize('json', d):
            logger.warning(obj.object) ## return the django model class object 

    elif event.type == 'payment_method.attached':
        logger.warning("============PAYMENT METHOD ATTACHED=================")
        payment_method = event.data.object # contains a stripe.PaymentMethod
        # Then define and call a method to handle the successful attachment of a PaymentMethod.
        # handle_payment_method_attached(payment_method)
    # ... handle other event types
    else:
        print('Unhandled event type {}'.format(event.type))

    return HttpResponse(status=200)


@api_view(['POST'])
def prodigi_webhook(request):
    stripe.api_key = os.environ.get('STRIPE_TEST_SECRET_KEY')
    logger.warning("============EVENTS PRODIGI=================")

    # create a CloudEvent
    event = from_http(request.headers, request.body)
    logger.warning("============EVENTS TYPE=================")
    logger.warning(event['type'])
    event_type = event['type'].split(".")
    assert(".".join(event_type[0:2]) == "com.prodigi")
    if (".".join(event_type[2:-1]) == "order.status.stage"):
        # Process order events
        event_action_value = event_type[-1].split("#")
        if event_action_value[0] == "changed":
            # Process the order status changes.
            logger.warning(event.data)
            stripe.PaymentIntent.modify(
                event.data["order"]["merchantReference"],
                metadata={
                    "order_id": "6735",
                    "stage": event_action_value[1],
                }
            )
    elif (".".join(event_type[2:-1]) == "order.shipments"):
        # Process order events
        event_action_value = event_type[-1].split("#")
        if event_action_value[0] == "shipment":
            # Process the shipment completion.
            logger.warning(event.data)
    else:
        None
    # prodigi_event  = json.loads(request.body)
    # logger.warning(prodigi_event)
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


def stripe_to_prodigi_shipping_address(stripe_address):
    logger.warning(stripe_address)
    return {
        "line1": stripe_address["line1"],
        "line2": stripe_address["line2"],
        "townOrCity": stripe_address["city"],
        "stateOrCounty": stripe_address["state"],
        "countryCode": stripe_address["country"],
        "postalOrZipCode": stripe_address["postal_code"],
    }
