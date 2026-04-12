from django import forms
from .models import Client

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            "firstname", "middlename", "lastname", "phonenumber",
            "date_of_birth", "marital_status",
            "employername", "idara", "kaziyako", "employmentcardno",
            "tareheya_kuajiriwa", "umri_kazini", "tarehe_ya_kustaafu",
            "region", "district", "street",
            "checkno", "mkoa", "wilaya", "tarafa", "kata", "mtaa",
            "wategemezi_wako",
            "bank_name", "bank_branch", "bank_account_number",
            "account_name", "account_type",
            # Taarifa za Mdhamini
            "mdhamini_jina_kamili", "mdhamini_checkno",
            "mdhamini_kitambulisho_kazi", "mdhamini_kazi",
            "mdhamini_kituo_kazi", "mdhamini_kata", "mdhamini_tarafa",
            "mdhamini_wilaya", "mdhamini_mkoa", "mdhamini_simu",
        ]
