from pyforge.lib import exceptions

class SFXError(exceptions.ToolError): pass
class SFXIllegalProject(SFXError): pass
class SFXAPIError(SFXError): pass
class SFXBadRequest(SFXAPIError): pass
class SFXUnauthorized(SFXAPIError): pass
class SFXForbidden(SFXAPIError): pass
class SFXNotFound(SFXAPIError): pass
class SFXGone(SFXAPIError): pass


SFXAPIError.status_map = {
        400:SFXBadRequest,
        401:SFXUnauthorized,
        403:SFXForbidden,
        404:SFXNotFound,
        409:exceptions.ProjectConflict,
        410:SFXGone }
