# Entry point for the application.
# import logging
from vfzsync import app    # For application discovery by the 'flask' command. 
import vfzsync.vfz_routes  # For import side-effects of setting up routes. 

if __name__ == "__main__":
    # if run through Flask
    app.run(host='0.0.0.0')
else:
    # if run through gunicorn
    # gunicorn_logger = logging.getLogger('gunicorn.error')
    # app.logger.handlers = gunicorn_logger.handlers
    # app.logger.setLevel(gunicorn_logger.level)
    # app.logger.warn('warn')
    pass


# error hander #todo
# import werkzeug
# @app.errorhandler(werkzeug.exceptions.InternalServerError)
# def handle_bad_request(e):
#     return 'bad request!', 500
# @app.errorhandler(werkzeug.exceptions.BadRequest)
# def handle_bad_request(e):
#     return 'bad request!', 400