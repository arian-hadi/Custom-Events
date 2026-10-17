import re
from urllib.parse import urlsplit

from django import forms
from django.conf import settings

from .amazon_models import AmazonSource, MARKETPLACES


def product_identity(link):
    """Extract product identity locally; never request an administrator-supplied URL."""
    link = link.strip()
    if '://' not in link:
        link = 'https://' + link
    try:
        url = urlsplit(link)
        host = (url.hostname or '').lower()
        if host in {'amzn.to', 'a.co'}:
            raise forms.ValidationError('Open this short link in your browser, then paste the full Amazon product URL from the address bar.')
        marketplace = 'www.' + re.sub(r'^(www\.|m\.)', '', host)
        if (url.scheme not in {'https', 'http'} or url.username or url.password or url.port
                or marketplace not in MARKETPLACES or '\\' in link):
            raise forms.ValidationError('Paste a product link from a supported Amazon website.')
        match = re.search(r'/(?:dp|gp/product|gp/aw/d)/([A-Za-z0-9]{10})(?:/|$)', url.path)
        if not match:
            raise forms.ValidationError('This link does not contain a product ASIN. Open the product itself and copy its full address.')
        return match.group(1).upper(), marketplace
    except ValueError:
        raise forms.ValidationError('Enter a valid Amazon product link.') from None


class AmazonSourceForm(forms.ModelForm):
    product_url = forms.CharField(label='Amazon product link', required=False,
        widget=forms.TextInput(attrs={'class': 'vURLField', 'placeholder': 'https://www.amazon.com/dp/…'}),
        help_text='Paste the full product link. Saving extracts its ASIN and marketplace automatically. For short share links, open them first and copy the full address.')

    class Meta:
        model = AmazonSource
        fields = ('product_url', 'asin', 'marketplace', 'enabled', 'publish')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['asin'].required = False
            self.fields['asin'].help_text = 'Optional when a product link is supplied. Otherwise enter the ten-character ASIN.'
            self.fields['marketplace'].required = False
            self.fields['marketplace'].initial = getattr(settings, 'AMAZON_MARKETPLACE', 'www.amazon.com')
            self.fields['marketplace'].help_text = 'Automatically taken from the product link when supplied.'

    def clean(self):
        data = super().clean()
        if self.instance.pk:
            return data
        link = data.get('product_url')
        if link:
            try:
                asin, marketplace = product_identity(link)
            except forms.ValidationError as exc:
                self.add_error('product_url', exc)
                return data
            if data.get('asin') and data['asin'].upper() != asin:
                self.add_error('asin', 'This ASIN does not match the product link. Clear it to use the link.')
            else:
                data['asin'] = asin
            data['marketplace'] = marketplace
        else:
            data['asin'] = (data.get('asin') or '').upper()
            data['marketplace'] = data.get('marketplace') or getattr(settings, 'AMAZON_MARKETPLACE', 'www.amazon.com')
        return data
