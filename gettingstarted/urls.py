from django.urls import path, include

from django.contrib import admin

admin.autodiscover()

import hello.views

# To add a new path, first import the app:
# import blog
#
# Then add the new path:
# path('blog/', blog.urls, name="blog")
#
# Learn more here: https://docs.djangoproject.com/en/2.1/topics/http/urls/

urlpatterns = [
    path("", hello.views.index, name="index"),
    path("db/", hello.views.db, name="db"),
    path("admin/", admin.site.urls),
    path("get_quote", hello.views.get_quote, name="get_quote"),
    path("get_quotes", hello.views.get_quotes, name="get_quotes"),
    path("create_payment_intent", hello.views.create_payment_intent, name="create_payment_intent"),
    path("ephemeral_keys", hello.views.ephemeral_keys, name="ephemeral_keys"), 
    path("stripe_webhook", hello.views.stripe_webhook, name="stripe_webhook"), 
    path("prodigi_webhook", hello.views.prodigi_webhook, name="prodigi_webhook"),
    # path("admin/", admin.site.urls),
    # path("admin/", admin.site.urls),

]
