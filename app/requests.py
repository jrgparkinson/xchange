from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.contrib.auth import logout
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import authenticate, login
from app.forms import SignUpForm
from app.models import *
from django.contrib.auth.decorators import login_required
