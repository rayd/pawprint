from csfam.pawprint.handlers import LoginService, GetAllTickets, GetTicketTypes,\
    GetTicketStates, GetTicketVersions, GetTicketSeverities, GetTicketResolutions,\
    GetTicketPriorities, GetMilestones, GetComponents
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

application = webapp.WSGIApplication([
    ('/login', LoginService),
    ('/ticket/getAll', GetAllTickets),
    ('/ticket/meta/getTypes', GetTicketTypes),
    ('/ticket/meta/getStates', GetTicketStates),
    ('/ticket/meta/getVersions', GetTicketVersions),
    ('/ticket/meta/getSeverities', GetTicketSeverities),
    ('/ticket/meta/getResolutions', GetTicketResolutions),
    ('/ticket/meta/getPriorities', GetTicketPriorities),
    ('/milestone/getAll', GetMilestones),
    ('/component/getAll', GetComponents)
], debug=True)

def main():
    run_wsgi_app(application)

if __name__ == '__main__':
    main()