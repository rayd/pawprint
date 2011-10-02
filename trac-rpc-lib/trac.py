import logging
import json
import auth
from google.appengine.ext import webapp
from xmlrpclib import ServerProxy
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
        """All Trac Request classes need to implement this -- they should 
        write out to the response if there's a success or raise a TracError instance
        if something goes wrong with the request"""
        raise NotImplementedError("all Trac Request classes need to implement this")
    
    def post(self):
        """Takes care of basic process of handling a TracRequest. Most subclasses of
        this class shouldn't have to override the post() method"""
        token = self.request.get('token')
        # TODO: need to explore the implications of the "eventually consistent"
        # datastore for this query which is not an "ancestor query" 
        session = Session.gqp("WHERE token = :t", t=token).get()
        
        try:
            if session == None:
                raise SessionExpiredError()
            else:
                # if we have a good session, call the handle function
                # of the specific implementation of the TracRequestHandler
                handle(proxy(session))
        except TracError as te:
            self.response.out.write(trac_error_to_response(te))
            logger.error(str(te))
        except Exception as e:
            self.response.out.write(trac_error_to_response(TracError(000, "Unknown error: {0}".format(str(e)))))
            logger.error(str(e))


def trac_error_to_response(err):

    return json.dumps({'success': False, 
                       'reason': {'errcode': err.code, 
                                  'errmsg' : err.msg }})


class TracError(Exception):
    def __init__(self, code, msg):
        self.code = code
        self.msg = msg
    
    def __str__(self):
        return str("{0}: {1}".format(self.code, self.msg))


class SessionExpiredError(TracError):
    def __init__(self):
        self.code = 317
        self.msg = "session has expired"
        

class AuthenticationError(TracError):
    def __init__(self, code, msg):
        self.code = code
        self.msg = "Authentication error: {0}".format(msg)
    
    def __str__(self):
        return str("{0}: {1}".format(self.code, self.msg))


class UnsupportedMethodError(TracError):
    def __init__(self, method_name):
        self.code = 327
        self.msg = "the method '{0}' is not supported by the Trac server".format(method_name)