import markdown
from pyforge import model as M

class ArtifactLinkProcessor(markdown.preprocessors.Preprocessor):
    def run(self, lines):
        new_lines = []
        re = M.ArtifactLink.re_link
        lookup = M.ArtifactLink.lookup
        def replace_link(mo):
            old_link = mo.group(0)
            new_link = lookup(old_link)
            if new_link:
                return '[<a href="%s">%s</a>]' % (new_link.url, old_link[1:-1])
            else:
                return old_link
        for line in lines:
            line = re.sub(replace_link, line)
            new_lines.append(line)
        return new_lines

class ArtifactExtension(markdown.Extension):
    def extendMarkdown(self, md, md_globals):
        md.preprocessors['artifactlink'] = ArtifactLinkProcessor(md)
