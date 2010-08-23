class ForgeError(Exception): pass
class ProjectConflict(ForgeError): pass
class ToolError(ForgeError): pass
class NoSuchProjectError(ForgeError): pass
