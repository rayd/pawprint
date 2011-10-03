from csfam.pawprint.traclib import user_session, cleanup_session, \
    MissingRequiredParameterError, Session, SessionExpiredError, proxy, TracError, \
    trac_error_to_response, DoesNotSupportRPCError, protocol_error_to_trac_error, \
    fault_error_to_trac_error
from google.appengine.ext import webapp
from xmlrpclib import ResponseError, ProtocolError, Fault
import json
import logging


class TracRequestHandler(webapp.RequestHandler):
    def handle(self, proxy):
        """All Trac Request classes MUST implement this -- they should 
        write out to the response if request is successful or raise a TracError 
        instance if something goes wrong with the request
        
        We can rely on this class to catch errors.
        """
        raise NotImplementedError("all Trac Request classes need to implement this")
    
    def caught_error(self, err, session):
        """This method SHOULD be implemented by subclasses of TracRequestHandler
        so they can deal with error that occur during the processing of the
        Trac request. We can't guarantee that session has a value."""
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
            self.caught_error(te, session)
        except ResponseError as re:
            if session == None:
                url = ""
            else:
                url = session.trac_url
            self.response.out.write(trac_error_to_response(DoesNotSupportRPCError(url)))
            logging.warn("error handling Trac request -- bad response: {0}", str(re))
            self.caught_error(re, session)
        except ProtocolError as pe:
            self.response.out.write(trac_error_to_response(protocol_error_to_trac_error(pe)))
            logging.warn("error handling Trac request -- protocol error: {0}".format(str(pe)))
            self.caught_error(pe, session)
        except Fault as f:
            self.response.out.write(trac_error_to_response(fault_error_to_trac_error(f)))
            logging.warn("error handling Trac request -- fault: {0}".format(str(f)))
            self.caught_error(f, session)
        except Exception as e:
            self.response.out.write(trac_error_to_response(TracError(msg = "unknown error: {0}".format(str(e)))))
            logging.error("error handling Trac request: {0}", str(e))
            self.caught_error(e, session)    


class LoginService(TracRequestHandler):
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
        try:
            session = None
            url = self.request.get('url');
            username = self.request.get('username')
            password = self.request.get('password')
            if url == None:
                raise MissingRequiredParameterError('url')
            elif username == None:
                raise MissingRequiredParameterError('username')
            elif password == None:
                raise MissingRequiredParameterError('password')            
    
            session = user_session(url, username, password)
            self.response.out.write(json.dumps({'success': True, 'token': session.token}))
        except TracError as te:
            self.response.out.write(trac_error_to_response(te))
            logging.warn("error handling Trac request: {0}", str(te))
            self.caught_error(te, session)
        except ResponseError as re:
            self.response.out.write(trac_error_to_response(DoesNotSupportRPCError(url)))
            logging.warn("error handling Trac request -- bad response: {0}", str(re))
            self.caught_error(re, session)
        except ProtocolError as pe:
            self.response.out.write(trac_error_to_response(protocol_error_to_trac_error(pe)))
            logging.warn("error handling Trac request -- protocol error: {0}".format(str(pe)))
            self.caught_error(pe, session)
        except Fault as f:
            self.response.out.write(trac_error_to_response(fault_error_to_trac_error(f)))
            logging.warn("error handling Trac request -- fault: {0}".format(str(f)))
            self.caught_error(f, session)
        except Exception as e:
            self.response.out.write(trac_error_to_response(TracError(msg = "unknown error: {0}".format(str(e)))))
            logging.error("error handling Trac request: {0}", str(e))
            self.caught_error(e, session)

    def caught_error(self, err, session):
        if session != None:
            cleanup_session(session)