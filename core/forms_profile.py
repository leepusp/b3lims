import re

from django import forms

from core.models import UserProfile


ORCID_PATTERN = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")


class UserProfileForm(forms.ModelForm):
    """Edit Django identity fields and B3 LIMS scientific profile data."""

    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)

    class Meta:
        model = UserProfile
        fields = (
            "first_name",
            "last_name",
            "email",
            "preferred_name",
            "institution",
            "department",
            "orcid",
            "phone",
            "expertise",
            "biography",
            "profile_visibility",
        )
        widgets = {
            "expertise": forms.Textarea(attrs={"rows": 3}),
            "biography": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["first_name"].initial = user.first_name
        self.fields["last_name"].initial = user.last_name
        self.fields["email"].initial = user.email

        for field in self.fields.values():
            css_class = "form-select" if isinstance(
                field.widget,
                forms.Select,
            ) else "form-control"
            field.widget.attrs["class"] = css_class

    def clean_orcid(self):
        value = self.cleaned_data.get("orcid", "").strip().upper()
        if not value:
            return ""
        if not ORCID_PATTERN.fullmatch(value):
            raise forms.ValidationError(
                "Enter an ORCID in the format 0000-0000-0000-0000."
            )

        digits = value.replace("-", "")
        total = 0
        for digit in digits[:15]:
            total = (total + int(digit)) * 2
        result = (12 - (total % 11)) % 11
        expected = "X" if result == 10 else str(result)
        if digits[-1] != expected:
            raise forms.ValidationError("Enter a valid ORCID checksum.")
        return value

    def save(self, commit=True):
        profile = super().save(commit=False)
        profile.user = self.user

        if commit:
            self.user.first_name = self.cleaned_data["first_name"].strip()
            self.user.last_name = self.cleaned_data["last_name"].strip()
            self.user.email = self.cleaned_data["email"].strip()
            self.user.save(
                update_fields=("first_name", "last_name", "email"),
            )
            profile.save()

        return profile
