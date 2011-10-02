from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
#from csfam.pawprint.auth import LoginService
from csfam.pawprint.auth import LoginService


application = webapp.WSGIApplication([
    ('/login', LoginService)
], debug=True)

def main():
    run_wsgi_app(application)

if __name__ == '__main__':
    main()