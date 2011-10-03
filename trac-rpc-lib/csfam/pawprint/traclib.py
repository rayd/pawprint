from datetime import datetime, timedelta
from google.appengine.ext import db
from urlparse import urlunparse, urlparse
from uuid import uuid4
from xmlrpclib import ServerProxy
import json
import logging
import xmlrpclib

# token duration in seconds
TOKEN_DURATION = 60

# dict storing ServerProxy objects associated with a user's token/session 
stored_proxies = dict()

class Session(db.Model):
    """Models a user's login session with the following fields:
        - token
        - username
        - password
        - trac_url
        - expiry
    """
    token = db.StringProperty(required=True)
    trac_url = db.StringProperty(required=True)
    username = db.StringProperty(required=True)
    password = db.StringProperty(required=True)
    expiry = db.DateTimeProperty(required=True)


def session_group_key(url):
    """Constructs a datastore key for a SessionGroup
    entity with the given url"""
    return db.Key.from_path('SessionGroup', url)

    
def user_session(url, username, password):
    """Gets a Session object for a user/url combo from the
    datastore or creates a new one if necessary.
    """
    session = Session.gql("WHERE ANCESTOR IS :key "
                           "AND username = :user "
                           "AND password = :pw "
                           "AND expiry > :ex "
                           "ORDER BY expiry DESC",
                           key=session_group_key(url),
                           user=username,
                           pw=password,
                           ex=datetime.now()).get()
    
    if session == None:
        # if we don't have a valid session, authenticate 
        # the user and create a new session
        
        # a token should expire after a specified amount of time
        valid_duration = timedelta(seconds=TOKEN_DURATION)

        session = Session(parent=session_group_key(url),
                          trac_url=url,
                          username=username,
                          password=password,
                          token=str(uuid4()),
                          expiry=(datetime.now() + valid_duration))
        session.put()
        logging.debug("stored a new user session")
        
        # authenticate!
        authenticate(session)        
    else:
        logging.debug("""
            found session:
                username: %s
                password: %s
                url: %s
                token: %s
                expiry: %s
            """,
            session.username,
            session.password,
            session.trac_url,
            session.token,
            session.expiry)

    return session


def authenticate(session):
    """Authenticates the user with the information provided in the
    Session object. Returns True if successful, otherwise throws an
    AuthenticationError with an error code and message"""
    proxy(session).system.getAPIVersion()
    return True


def cleanup_session(session):
    remove_proxy(session)
    try:
        session.delete()
    except db.NotSavedError:
        logging.error("tried removing a session that was not saved")


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


def trac_error_to_response(err):
    """Transforms a TracError class into a client-understandable
    JSON string with error details"""
    return json.dumps({'success': False, 
                       'reason': {'errcode': err.code, 
                                  'errmsg' : err.msg }})


def protocol_error_to_trac_error(pe):
    """Transforms an xmlrpclib.ProtocolError into proper subclass
    of TracError based on ProtocolError.errcode value"""
    if pe.errcode == 404:
        return ServerCannotBeFoundError(pe.url)
    elif pe.errcode == 401:
        # parse url to get username
        return AuthenticationError(pe.url.split(':')[0], pe.url)
    elif pe.errcode == 405:
        return DoesNotSupportRPCError(pe.url)
    else:
        return TracError(msg = "unknown protocol error: {0}".format(str(pe)))

def fault_error_to_trac_error(fault):
    """Transforms an xmlrpclib.Fault into proper subclass
    of TracError based on Fault.faultCode value. Fault types
    are based on the info found here: 
    http://xmlrpc-epi.sourceforge.net/specs/rfc.fault_codes.php"""
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
    """Base error class that all Trac errors should inherit from"""
    def __init__(self, code, msg):
        self.code = code or 999
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
    def __init__(self, user, url):
        TracError.__init__(self, 337, "could not authenticate user '{0}' for '{1}'".format(user, url))

        
class DoesNotSupportRPCError(TracError):
    def __init__(self, url):
        TracError.__init__(self, 347, "the specified Trac server '{0}' does not support RPC".format(url))


## Exceptions mapping to specific fault errors defined in xmlrpclib
class TracFaultError(TracError):
    """General Fault error of which there are many subclasses"""
    def __init__(self, code, msg):
        TracError.__init__(self, code or 998, "fault -- {0}".format(msg))


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