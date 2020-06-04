from django.conf import settings # import the settings file

def deploy_url(request):
    # return the value you want as a dictionnary. you may add multiple values in there.
    return {'DEPLOY_URL': settings.DEPLOY_URL}