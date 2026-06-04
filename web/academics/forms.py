from django import forms
from .models import Department, Subject, SubjectTeacher
from accounts.models import CustomUser


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'code', 'hod', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Computer Engineering'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., COMP',
                'style': 'text-transform: uppercase;'
            }),
            'hod': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['hod'].queryset = CustomUser.objects.filter(
            role__in=['teacher', 'hod'], is_active=True
        )
        self.fields['hod'].required = False


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ['name', 'code', 'department', 'semester', 'credit_hours']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Operating Systems'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., CE801',
                'style': 'text-transform: uppercase;'
            }),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'semester': forms.NumberInput(attrs={
                'class': 'form-control', 'min': 1, 'max': 8
            }),
            'credit_hours': forms.NumberInput(attrs={
                'class': 'form-control', 'min': 1, 'max': 6
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['department'].queryset = Department.objects.filter(is_active=True)


class SubjectTeacherForm(forms.ModelForm):
    class Meta:
        model = SubjectTeacher
        fields = ['teacher', 'subject']
        widgets = {
            'teacher': forms.Select(attrs={'class': 'form-select'}),
            'subject': forms.Select(attrs={'class': 'form-select'}),
        }


class TeacherForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Set password'
        }),
        required=True,
        min_length=4,
    )

    class Meta:
        model = CustomUser
        fields = ['username', 'full_name', 'email', 'department', 'phone']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'e.g., prof.sharma'
            }),
            'full_name': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Full name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control', 'placeholder': 'Email (optional)'
            }),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'phone': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Phone (optional)'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['department'].queryset = Department.objects.filter(is_active=True)
        self.fields['email'].required = False
        self.fields['phone'].required = False


class TeacherEditForm(forms.ModelForm):
    """Edit teacher — no password field."""
    class Meta:
        model = CustomUser
        fields = ['full_name', 'email', 'department', 'phone']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['department'].queryset = Department.objects.filter(is_active=True)
        self.fields['email'].required = False
        self.fields['phone'].required = False


class StudentForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Default: same as roll number'
        }),
        required=False,
        help_text='Leave blank to use roll number as password.',
    )

    class Meta:
        model = CustomUser
        fields = ['roll_no', 'full_name', 'department', 'semester', 'email', 'phone']
        widgets = {
            'roll_no': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'e.g., 780322'
            }),
            'full_name': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Full name'
            }),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'semester': forms.NumberInput(attrs={
                'class': 'form-control', 'min': 1, 'max': 8
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control', 'placeholder': 'Email (optional)'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Phone (optional)'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['department'].queryset = Department.objects.filter(is_active=True)
        self.fields['email'].required = False
        self.fields['phone'].required = False


class StudentEditForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ['full_name', 'department', 'semester', 'email', 'phone']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'semester': forms.NumberInput(attrs={
                'class': 'form-control', 'min': 1, 'max': 8
            }),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['department'].queryset = Department.objects.filter(is_active=True)
        self.fields['email'].required = False
        self.fields['phone'].required = False