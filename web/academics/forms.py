from django import forms
from .models import Batch, Department, Subject, SubjectTeacher
from accounts.models import CustomUser


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'code', 'roll_code', 'hod', 'is_active']
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
            'roll_code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 03',
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


class BatchForm(forms.ModelForm):
    class Meta:
        model = Batch
        fields = ['department', 'year', 'code', 'is_active']
        widgets = {
            'department': forms.Select(attrs={'class': 'form-select'}),
            'year': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 2000,
                'max': 2099,
                'placeholder': 'e.g., 2078 or 2026',
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 78 or 26',
                'maxlength': '2',
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['department'].queryset = Department.objects.filter(is_active=True)
        self.fields['code'].required = False
        self.fields['code'].help_text = 'Leave blank to auto-use the last 2 digits of the year.'


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
    batch_year = forms.IntegerField(
        label='Batch Year',
        min_value=2000,
        max_value=2099,
        help_text='Enter the intake year directly, e.g. 2026. The matching batch will be created or reused automatically.',
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g., 2026',
        }),
    )

    class Meta:
        model = CustomUser
        fields = ['department', 'full_name', 'semester', 'email', 'phone']
        widgets = {
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
        self.fields['department'].help_text = 'Choose the department first; batch will be resolved from year + department.'
        self.fields['email'].required = False
        self.fields['phone'].required = False

    def clean(self):
        cleaned_data = super().clean()
        department = cleaned_data.get('department')
        batch_year = cleaned_data.get('batch_year')

        if not department:
            self.add_error('department', 'Please select a department.')
            return cleaned_data

        if not batch_year:
            self.add_error('batch_year', 'Please enter a batch year.')
            return cleaned_data

        if not department.roll_code:
            self.add_error('department', 'Selected department is missing roll code. Set it first.')

        return cleaned_data


class StudentEditForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ['full_name', 'semester', 'email', 'phone']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'semester': forms.NumberInput(attrs={
                'class': 'form-control', 'min': 1, 'max': 8
            }),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'].required = False
        self.fields['phone'].required = False
