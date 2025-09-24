from django import forms
from django.contrib.auth.models import User
from .models import TeacherProfile, ParentProfile, StudentProfile, Student


class UserBaseForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
        }


class TeacherProfileForm(forms.ModelForm):
    class Meta:
        model = TeacherProfile
        fields = ["phone"]
        widgets = {"phone": forms.TextInput(attrs={"class": "form-control"})}


class ParentProfileForm(forms.ModelForm):
    class Meta:
        model = ParentProfile
        fields = ["phone"]
        widgets = {"phone": forms.TextInput(attrs={"class": "form-control"})}


class StudentProfileForm(forms.ModelForm):
    class Meta:
        model = StudentProfile
        fields = []  # حالياً مفيش حقول، مرتبط بـ student و user فقط


class StudentCoreForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ["school_name", "phone", "email"]
        widgets = {
            "school_name": forms.TextInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
        }
