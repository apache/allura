import re
import markdown
from pyforge import model as M

class ArtifactLinkProcessor(markdown.preprocessors.Preprocessor):
    def run(self, lines):
        new_lines = []
        # re = M.ArtifactLink.re_link
        lookup = M.ArtifactLink.lookup
        def replace_link(mo):
            old_link = mo.group(0)
            new_link = lookup(old_link)
            if new_link:
                link_text = ':'.join(
                    g for g in mo.groups() if g is not None)
                return ' [<a href="%s">%s</a>]' % (new_link.url, link_text)
            else:
                return old_link
        for line in lines:
            line = M.ArtifactLink.re_link_1.sub(replace_link, line)
            line = M.ArtifactLink.re_link_2.sub(replace_link, line)
            new_lines.append(line)
        return new_lines

class AutolinkProcessor(markdown.preprocessors.Preprocessor):
    re_href = re.compile(r'\bhttp(?:s?)://\S*\b')
    def run(self, lines):
        new_lines = []
        # re = M.ArtifactLink.re_link
        lookup = M.ArtifactLink.lookup
        def replace_link(mo):
            old_link = mo.group(0)
            return '<a href="%s">%s</a>' % (old_link, old_link)
        return [ self.re_href.sub(replace_link, line)
                 for line in lines ]

class ForgeExtension(markdown.Extension):
    def extendMarkdown(self, md, md_globals):
        md.preprocessors['01_autolink'] = AutolinkProcessor(md)
        md.preprocessors['02_artifactlink'] = ArtifactLinkProcessor(md)
