from gc import callbacks
from django.db import models

# Create your models here.
class Greeting(models.Model):
    when = models.DateTimeField("date created", auto_now_add=True)

class PaymentIntent(models.Model):
    title = models.CharField(max_length=70, blank=False, default="default_title")
    description = models.CharField(max_length=200,blank=False, default="default_description")


class ProdigiDetails(models.Model):
    DetailValues = models.TextChoices('DetailValues', 'NotStarted InProgress Complete Error')

    downloadAssets = models.CharField(max_length=100, blank=False, choices=DetailValues.choices)
    allocateProductionLocation = models.CharField(max_length=100, blank=False, choices=DetailValues.choices)
    printReadyAssetsPrepared = models.CharField(max_length=100, blank=False, choices=DetailValues.choices)
    inProduction = models.CharField(max_length=100, blank=False, choices=DetailValues.choices)
    shipping = models.CharField(max_length=100, blank=False, choices=DetailValues.choices)

class ProdigiCost(models.Model):
    amount = models.CharField(max_length=100, blank=False)
    currency = models.CharField(max_length=100, blank=False)

class ProdigiAuthorisationDetails(models.Model):
    authorisationUrl = models.CharField(max_length=100, blank=False)
    paymentDetails = ProdigiCost()

class ProdigiIssues(models.Model):
    ErrorValues = models.TextChoices('ErrorValues', 'items.assets.NotDownloaded items.assets.FailedToDownloaded')
    objectId = models.CharField(max_length=100, blank=False)
    errorCode = models.CharField(max_length=100, blank=False, choices=ErrorValues.choices)
    description = models.CharField(max_length=100, blank=False)
    authorisationDetails = ProdigiAuthorisationDetails()

class ProdigiStatus(models.Model):
    stage = models.CharField(max_length=100, blank=False)
    details = ProdigiDetails()
    issues = ProdigiIssues()

class ProdigiChargeItem(models.Model):
    id =  models.CharField(max_length=100, unique=True, primary_key=True, blank=False)
    description = models.CharField(max_length=100, blank=False)
    itemSku = models.CharField(max_length=100, blank=False)
    shipmentId = models.CharField(max_length=100, blank=False)
    itemId = models.CharField(max_length=100, blank=False)
    merchantItemReference = models.CharField(max_length=100, blank=True)
    cost = ProdigiCost()

class ProdigiCharge(models.Model):
    id =  models.CharField(max_length=100, unique=True, primary_key=True, blank=False)
    prodigiInvoiceNumber = models.CharField(max_length=100, blank=False)
    totalCost = ProdigiCost()
    items = models.ManyToManyField('ProdigiChargeItem')

class ProdigiShipmentItem(models.Model):
    id =  models.CharField(max_length=100, unique=True, primary_key=True, blank=False)

class ProdigiFulfillmentLocation(models.Model):
    countryCode = models.CharField(max_length=100, blank=False)
    labCode = models.CharField(max_length=100, blank=False)

class ProdigiShipment(models.Model):
    id =  models.CharField(max_length=100, unique=True, primary_key=True, blank=False)
    carrier = models.CharField(max_length=100, blank=False)
    tracking = models.CharField(max_length=100, blank=False)
    dispatchDate = models.CharField(max_length=100, blank=False)
    items = models.ManyToManyField('ProdigiChargeItem')
    fulfillmentLocation = models.CharField(max_length=100, blank=True)

class ProdigiAddress(models.Model):
    line1 = models.CharField(max_length=100, blank=False)
    line2 = models.CharField(max_length=100, blank=True)
    postalOrZipCode = models.CharField(max_length=100, blank=False)
    countryCode = models.CharField(max_length=100, blank=False)
    townOrCity = models.CharField(max_length=100, blank=False)
    stateOrCounty = models.CharField(max_length=100, blank=True)

class ProdigiRecipient(models.Model):
    printArea = models.CharField(max_length=100, blank=False)
    url = models.CharField(max_length=100, blank=False)

class ProdigiAsset(models.Model):
    name = models.CharField(max_length=100, blank=False)
    email = models.CharField(max_length=100, blank=True)
    phoneNumber = models.CharField(max_length=100, blank=True)
    address = ProdigiAddress()

class ProdigiItem(models.Model):
    id =  models.CharField(max_length=100, unique=True, primary_key=True, blank=False)
    merchantReference = models.CharField(max_length=100, blank=True)
    sku = models.CharField(max_length=100, blank=False)
    copies = models.IntegerField(blank=False)
    sizing = models.CharField(max_length=100, blank=False)
    recipientCost = ProdigiCost()
    attributes = models.JSONField(blank=True)
    assets = models.ManyToManyField('ProdigiAsset')

class ProdigiPackingSlip(models.Model):
    url = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=100, blank=True)

class ProdigiOrder(models.Model):
    id =  models.CharField(max_length=100, unique=True, primary_key=True, blank=False)
    created = models.CharField(max_length=100, blank=False)
    callbackUrl = models.CharField(max_length=100, blank=True)
    merchantReference = models.CharField(max_length=100, blank=True)
    shippingMethod = models.CharField(max_length=100, blank=False)
    idempotencyKey = models.CharField(max_length=100, blank=True)
    status = ProdigiStatus()
    charges	 = models.ManyToManyField('ProdigiCharge')
    shipments = models.ManyToManyField('ProdigiShipment')
    recipient = ProdigiRecipient()
    items = models.ManyToManyField('ProdigiItem')
    packingSlip = ProdigiPackingSlip()
    metadata = models.JSONField()

    def get_charges(self):
        return "\n".join([p.charges for p in self.charges.all()])
    
    def get_shipments(self):
        return "\n".join([p.shipments for p in self.shipments.all()])

    def get_items(self):
        return "\n".join([p.items for p in self.items.all()])

