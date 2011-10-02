import logging
import trac
import json
from uuid import uuid4
from datetime import datetime, timedelta
from google.appengine.ext import webapp
from google.appengine.ext import db
from xmlrpclib import ProtocolError, Fault, ResponseError, Error

class LoginService(webapp.RequestHandler):
    """A post to this service should test authentication
    details against specified trac server, and if successful
    returns a token string, otherwise returns a failed JSON object
    
    post parameters:
        url: trac url (http://server/trac)
        username: username string
        password: password string
    
    returns json objects (as strings):
    success:
        { "success": true,
          "token": "14123j-4kjvjsfn-7skf13d-nv4-kl1234s"
        }
        
    failure:
        { "success": false,
          "reason": { "errcode": "error code",
                      "errmsg": "message explaining why auth failed"
                    }
        }
    """
    def post(self):
        url = self.request.get('url');
        username = self.request.get('username')
        password = self.request.get('password')
        logging.debug("url: %s username: %s password: %s",
                     url, username, password)

        try:
            session = user_session(url, username, password)
            self.response.out.write(json.dumps({'success': True, 'token': session.token}))
        except trac.AuthenticationError as e:
            self.response.out.write(trac.trac_error_to_response(e))

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
    datastore or creates a new one if necessary
    
    Returns None if there was """
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
        
        # a token should expire after 24 hours
        valid_duration = timedelta(seconds=60)#86400)

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
    try:
        trac.proxy(session).system.getAPIVersion()
    except ProtocolError as e1:
        # if we have a problem authenticating, let's clean the session out
        cleanup_session(session)
        raise trac.AuthenticationError(code=e1.errcode, msg=e1.errmsg)
    except Fault as e2:
        # if we have a problem authenticating, let's clean the session out
        cleanup_session(session)
        raise trac.AuthenticationError(code=e2.faultCode, msg=e2.faultString)
    except ResponseError:
        cleanup_session(session)
        raise trac.AuthenticationError(code='400', msg='Malformed Response -- server does not support RPC')
    except Error as e4:
        cleanup_session(session)
        raise trac.AuthenticationError(code='000', msg='Unknown error -- authentication failed {0}'.format(str(e4)))
    return True


def cleanup_session(session):
    trac.remove_proxy(session)
    try:
        session.delete()
    except db.NotSavedError:
        logging.error("tried removing a session that was not saved")
