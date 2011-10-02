from xmlrpclib import ServerProxy
from urlparse import urlparse, urlunparse
import logging

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