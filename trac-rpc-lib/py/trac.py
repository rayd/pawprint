import logging
import json
import xmlrpclib
from auth import Session
from google.appengine.ext import webapp
from xmlrpclib import ServerProxy, ResponseError, ProtocolError, Fault
from urlparse import urlparse, urlunparse

stored_proxies = dict()

def proxy(session):
    """Gets a stored ServerProxy for this user session or
    creates a new one, stores it in the dict, and returns it"""
    token = session.token
    proxy = stored_proxies.get(token)
    if proxy == None:
        logging.debug("original url: %s", session.trac_url)
        url_parts = urlparse(session.trac_url)
        auth_info = "{0}:{1}@".format(session.username, session.password)
        if url_parts.path.endswith('/'):
            path = "{0}login/rpc".format(url_parts.path)
        else:
            path = "{0}/login/rpc".format(url_parts.path) 
        url = urlunparse((url_parts.scheme,
                          auth_info + url_parts.netloc,
                          path,
                          url_parts.params,
                          url_parts.query,
                          url_parts.fragment))
        logging.debug("transformed url: %s", url)
        proxy = ServerProxy(url)
        stored_proxies[session.token] = proxy
    
    return proxy


def remove_proxy(session):
    """Removes the ServerProxy stored for this session"""
    try:
        del stored_proxies[session.token]
    except KeyError:
        logging.error("tried deleting a ServerProxy that didn't exist")
        

class TracRequestHandler(webapp.RequestHandler):
    def handle(self, proxy):
        """All Trac Request classes MUST implement this -- they should 
        write out to the response if request is successful or raise a TracError 
        instance if something goes wrong with the request"""
        raise NotImplementedError("all Trac Request classes need to implement this")
    
    def caught_error(self, err):
        """This method SHOULD be implemented by subclasses of TracRequestHandler
        so they can deal with error that occur during the processing of the
        Trac request"""
        pass
        
    def post(self):
        """Takes care of basic process of handling a TracRequest. Most subclasses of
        this class shouldn't have to override the post() method
        
        Trac requests must be accompanied by a 'token' parameter. This is used to
        map to a Session object which is required to make a request to the remote 
        Trac server"""
        
        try:
            token = self.request.get('token')
            
            if token == None:
                raise MissingRequiredParameterError('token')
            
            # TODO: need to explore the implications of the "eventually consistent"
            # datastore on this query which is not an "ancestor query" 
            session = Session.gql("WHERE token = :t", t=token).get()
        
            if session == None:
                raise SessionExpiredError(token)
            else:
                # if we have a good session, call the handle function
                # of the specific implementation of the TracRequestHandler
                self.handle(proxy(session))
        except TracError as te:
            self.response.out.write(trac_error_to_response(te))
            logging.warn("error handling Trac request: {0}", str(te))
            self.caught_error(te)
        except ResponseError as re:
            self.response.out.write(trac_error_to_response(DoesNotSupportRPCError(session.trac_url)))
            logging.warn("error handling Trac request -- bad response: {0}", str(re))
            self.caught_error(re)
        except ProtocolError as pe:
            self.response.out.write(trac_error_to_response(protocol_error_to_trac_error(pe, session)))
            logging.warn("error handling Trac request -- protocol error: {0}".format(str(pe)))
            self.caught_error(pe)
        except Fault as f:
            self.response.out.write(trac_error_to_response(fault_error_to_trac_error(f)))
            logging.warn("error handling Trac request -- fault: {0}".format(str(f)))
            self.caught_error(f)
        except Exception as e:
            self.response.out.write(trac_error_to_response(TracError(msg = "unknown error: {0}".format(str(e)))))
            logging.error("error handling Trac request: {0}", str(e))
            self.caught_error(e)


def trac_error_to_response(err):
    return json.dumps({'success': False, 
                       'reason': {'errcode': err.code, 
                                  'errmsg' : err.msg }})


def protocol_error_to_trac_error(pe, session):
    if pe.errcode == 404:
        return ServerCannotBeFoundError(session.trac_url)
    elif pe.errcode == 401:
        return AuthenticationError(session.username)
    elif pe.errcode == 405:
        return DoesNotSupportRPCError(session.trac_url)
    else:
        return TracError(msg = "unknown protocol error: {0}".format(str(pe)))

def fault_error_to_trac_error(fault):
    if fault.faultCode == xmlrpclib.NOT_WELLFORMED_ERROR:
        return BadlyFormedRequestError(fault.faultString)
    elif fault.faultCode == xmlrpclib.UNSUPPORTED_ENCODING:
        return BadEncodingError(fault.faultString)
    elif fault.faultCode == xmlrpclib.INVALID_ENCODING_CHAR:
        return BadCharactorForEncodingError(fault.faultString)
    elif fault.faultCode == xmlrpclib.INVALID_XMLRPC:
        return InvalidRPCError(fault.faultString)
    elif fault.faultCode == xmlrpclib.METHOD_NOT_FOUND:
        return UnsupportedMethodError(fault.faultString)
    elif fault.faultCode == xmlrpclib.INVALID_METHOD_PARAMS:
        return InvalidMethodParamsError(fault.faultString)
    elif fault.faultCode == xmlrpclib.INTERNAL_ERROR:
        return InternalServerError(fault.faultString)
    else:
        return TracFaultError(msg = fault.faultString)

##
## Error raised by the Trac RPC lib
##
class TracError(Exception):
    def __init__(self, code=999, msg):
        self.code = code
        self.msg = msg
    
    def __str__(self):
        return str("{0}: {1}".format(self.code, self.msg))

class MissingRequiredParameterError(TracError):
    def __init__(self, param_name):
        TracError.__init__(self, 307, "request is missing a required parameter '{0}'".format(param_name))

class SessionExpiredError(TracError):
    def __init__(self, token):
        TracError.__init__(self, 317, "session has expired for {0}".format(token))


class ServerCannotBeFoundError(TracError):
    def __init__(self, url):
        TracError.__init__(self, 327, "the specified Trac server '{0}' cannot be found".format(url))


class AuthenticationError(TracError):
    def __init__(self, user):
        TracError.__init__(self, 337, "could not authenticate user {0}".format(user))

        
class DoesNotSupportRPCError(TracError):
    def __init__(self, url):
        TracError.__init__(self, 347, "the specified Trac server '{0}' does not support RPC".format(url))


## Exceptions mapping to specific fault errors defined in xmlrpclib

class TracFaultError(TracError):
    def __init__(self, code=998, msg):
        TracError.__init__(self, code, "fault -- {0}".format(msg))


class InvalidRPCError(TracFaultError):
    def __init__(self, msg):
        TracFaultError.__init__(self, 356, msg)


class UnsupportedMethodError(TracFaultError):
    def __init__(self, msg):
        TracFaultError.__init__(self, 357, msg)


class InvalidMethodParamsError(TracFaultError):
    def __init__(self, msg):
        TracFaultError.__init__(self, 358, msg)


class InternalServerError(TracFaultError):
    def __init__(self, msg):
        TracFaultError.__init__(self, 359, msg)


class BadlyFormedRequestError(TracFaultError):
    def __init__(self, msg):
        TracFaultError.__init__(self, 367, msg)


class BadEncodingError(TracFaultError):
    def __init__(self, msg):
        TracFaultError.__init__(self, 368, msg)


class BadCharactorForEncodingError(TracFaultError):
    def __init__(self, msg):
        TracFaultError.__init__(self, 369, msg)