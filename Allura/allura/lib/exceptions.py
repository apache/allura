class ForgeError(Exception): pass
class ProjectConflict(ForgeError): pass
class ProjectOverlimitError(ForgeError): pass
class ToolError(ForgeError): pass
class NoSuchProjectError(ForgeError): pass
class NoSuchNeighborhoodError(ForgeError): pass
class MailError(ForgeError): pass
class AddressException(MailError): pass
class NoSuchNBLevelError(ForgeError): pass

class CompoundError(ForgeError):
    def __repr__(self):
        return '<%s>\n%s\n</%s>'  % (
            self.__class__.__name__,
            '\n'.join(map(repr, self.args)),
            self.__class__.__name__)
    def format_error(self):
        import traceback
        parts = [ '<%s>\n' % self.__class__.__name__ ]
        for tp,val,tb in self.args:
            for line in traceback.format_exception(tp,val,tb):
                parts.append('    ' + line)
        parts.append('</%s>\n' % self.__class__.__name__ )
        return ''.join(parts)
                
