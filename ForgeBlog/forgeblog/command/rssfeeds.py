import re
import base


from forgeblog.main import ForgeBlogApp





re_amp = re.compile(r'''
    [&]          # amp
    (?=          # look ahead for:
      ([a-zA-Z0-9]+;)  # named HTML entity
      |
      (\#[0-9]+;)      # decimal entity
      |
      (\#x[0-9A-F]+;)  # hex entity
    )
    ''', re.VERBOSE)
re_leading_spaces = re.compile(r'^[ ]+', re.MULTILINE)
re_preserve_spaces = re.compile(r'''
    [ ]           # space
    (?=[ ])       # lookahead for a space
    ''', re.VERBOSE)
re_angle_bracket_open = re.compile('<')
re_angle_bracket_close = re.compile('>')
def plain2markdown(text, preserve_multiple_spaces=False, has_html_entities=False):
    return text


class RssFeedsCommand(base.BlogCommand):
    summary = 'Rss feed client'
