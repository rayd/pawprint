from csfam.pawprint.handlers import LoginService, GetAllTickets
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

application = webapp.WSGIApplication([
    ('/login', LoginService),
    ('/ticket/getAll', GetAllTickets)
], debug=True)

def main():
    run_wsgi_app(application)

if __name__ == '__main__':
    main()