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

class ArtifactExtension(markdown.Extension):
    def extendMarkdown(self, md, md_globals):
        md.preprocessors['artifactlink'] = ArtifactLinkProcessor(md)
