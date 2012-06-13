import re

from formencode import validators as fev

import ew as ew_core
import ew.jinja2_ew as ew

from allura.lib.widgets.forms import ForgeForm

class ValidateSvnUrl(fev.URL):
    url_re = re.compile(r'''
        ^(http|https|svn)://
        (?:[%:\w]*@)?                              # authenticator
        (?P<domain>[a-z0-9][a-z0-9\-]{,62}\.)*     # subdomain
        (?P<tld>[a-z]{2,63}|xn--[a-z0-9\-]{2,59})  # top level domain
        (?::[0-9]{1,5})?                           # port
        # files/delims/etc
        (?P<path>/[a-z0-9\-\._~:/\?#\[\]@!%\$&\'\(\)\*\+,;=]*)?
        $
    ''', re.I | re.VERBOSE)

class ImportForm(ForgeForm):
    submit_text='Import'
    class fields(ew_core.NameList):
        checkout_url = ew.TextField(label='Checkout URL',
                                    validator=ValidateSvnUrl(not_empty=True))
