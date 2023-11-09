# This script starts a simple Python webserver using Tornado.
# It handles requests from ReportBro Designer so pdf and xlsx reports
# can be previewed in the Designer.
#
# There is no application data and no report templates are stored.
# To store report templates you need an additional table and handle the request for saving.
# For a complete demo have a look at the Album-App available for Django, Flask and web2py.

from os import environ as env
from pathlib import Path
from reportbro import Report, ReportBroError
from sqlalchemy import create_engine, select
from sqlalchemy import func
from sqlalchemy import Table, Column, BLOB, Boolean, DateTime, Integer, String, Text, MetaData
from tornado.web import HTTPError
import logging
import datetime
import decimal
import json
import tornado.ioloop
import tornado.web
import uuid

BASE_DIR = Path(__file__).resolve().parent

SERVER_PORT = env.get('REPORTBRO_SERVER_PORT', 8000)
SERVER_PATH = env.get('REPORTBRO_SERVER_PATH', '/reportbro/report/run')
MAX_CACHE_SIZE = int(env.get('REPORTBRO_MAX_CACHE_SIZE', 500 * 1024 * 1024))  # keep max. 500 MB of generated pdf files in sqlite db

logger = logging.getLogger('tornado.access')

engine = create_engine('sqlite:///:memory:', echo=False)
db_connection = engine.connect()
metadata = MetaData()
report_request = Table(
    'report_request', metadata,
    Column('id', Integer, primary_key=True),
    Column('key', String(36), nullable=False),
    Column('report_definition', Text, nullable=False),
    Column('data', Text, nullable=False),
    Column('is_test_data', Boolean, nullable=False),
    Column('pdf_file', BLOB),
    Column('pdf_file_size', Integer),
    Column('created_on', DateTime, nullable=False))

metadata.create_all(engine)


# method to handle json encoding of datetime and Decimal
def jsonconverter(val):
    if isinstance(val, datetime.datetime):
        return '{date.year}-{date.month}-{date.day}'.format(date=val)
    if isinstance(val, decimal.Decimal):
        return str(val)


def raise_bad_request(*, reason, exception=None, report_errors=None):
    logger.warning(f'BAD REQUEST - "{reason}" - report_errors: {report_errors}', exc_info=exception)
    raise HTTPError(400, reason=reason)


class MainHandler(tornado.web.RequestHandler):
    def initialize(self, db_connection):
        self.db_connection = db_connection
        # if using additional fonts then add to this list
        self.additional_fonts = []

    def set_access_headers(self):
        self.set_header('Access-Control-Allow-Origin', '*')
        self.set_header('Access-Control-Allow-Methods', 'GET, PUT, OPTIONS')
        self.set_header('Access-Control-Allow-Headers', 'Origin, X-Requested-With, X-HTTP-Method-Override, Content-Type, Accept, Z-Key')

    def options(self):
        # options request is usually sent by browser for a cross-site request, we only need to set the
        # Access-Control-Allow headers in the response so the browser sends the following get/put request
        self.set_access_headers()

    def put(self):
        # all data needed for report preview is sent in the initial PUT request, it contains
        # the format (pdf or xlsx), the report itself (report_definition), the data (test data
        # defined within parameters in the Designer) and is_test_data flag (always True
        # when request is sent from Designer)
        self.set_access_headers()
        json_data = json.loads(self.request.body.decode('utf-8'))
        report_definition = json_data.get('report')
        output_format = json_data.get('outputFormat')
        if output_format not in ('pdf', 'xlsx'):
            raise_bad_request(reason=f'outputFormat parameter missing or invalid (output_format={output_format})')
        data = json_data.get('data')
        is_test_data = bool(json_data.get('isTestData'))

        try:
            report = Report(report_definition, data, is_test_data, additional_fonts=self.additional_fonts)
        except Exception as exception:
            raise_bad_request(reason='failed to initialize report', exception=exception)

        if report.errors:
            # return list of errors in case report contains errors, e.g. duplicate parameters.
            # with this information ReportBro Designer can select object containing errors,
            # highlight erroneous fields and display error messages
            self.write(json.dumps(dict(errors=report.errors)))
            return

        try:
            now = datetime.datetime.now()

            # delete old reports (older than 3 minutes) to avoid table getting too big
            self.db_connection.execute(report_request.delete().where(
                report_request.c.created_on < (now - datetime.timedelta(minutes=3)))
            )

            total_size = self.db_connection.execute(select([func.sum(report_request.c.pdf_file_size)])).scalar()
            if total_size and total_size > MAX_CACHE_SIZE:
                # delete all reports older than 10 seconds to reduce db size for cached pdf files
                self.db_connection.execute(report_request.delete().where(
                    report_request.c.created_on < (now - datetime.timedelta(seconds=10)))
                )

            report_file = report.generate_pdf()

            key = str(uuid.uuid4())
            # add report request into sqlite db, this enables downloading the report by url
            # (the report is identified by the key) without any post parameters.
            # This is needed for pdf and xlsx preview.
            self.db_connection.execute(
                report_request.insert(),
                key=key, report_definition=json.dumps(report_definition),
                data=json.dumps(data, default=jsonconverter), is_test_data=is_test_data,
                pdf_file=report_file, pdf_file_size=len(report_file), created_on=now)

            self.write('key:' + key)
        except ReportBroError as exception:
            # in case an error occurs during report generation a ReportBroError exception is thrown
            # to stop processing. We return this error within a list so the error can be
            # processed by ReportBro Designer.
            logger.warning('Error handled by ReportBro Designer', exc_info=exception)
            report_errors = dict(errors=[exception.error])
            self.write(json.dumps((report_errors)))
            return

    def get(self):
        self.set_access_headers()
        output_format = self.get_query_argument('outputFormat')
        assert output_format in ('pdf', 'xlsx')
        key = self.get_query_argument('key', '')
        report = None
        report_file = None
        if key and len(key) == 36:
            # the report is identified by a key which was saved
            # in an sqlite table during report preview with a PUT request
            row = self.db_connection.execute(select([report_request]).where(report_request.c.key == key)).fetchone()
            if not row:
                raise_bad_request(reason='report not found (preview probably too old), update report preview and try again')
            if output_format == 'pdf' and row['pdf_file']:
                report_file = row['pdf_file']
            else:
                report_definition = json.loads(row['report_definition'])
                data = json.loads(row['data'])
                is_test_data = row['is_test_data']
                report = Report(report_definition, data, is_test_data, additional_fonts=self.additional_fonts)
                if report.errors:
                    raise_bad_request(reason='error generating report', report_errors=report.errors)
        else:
            # in case there is a GET request without a key we expect all report data to be available.
            # this is NOT used by ReportBro Designer and only added for the sake of completeness.
            json_data = json.loads(self.request.body.decode('utf-8'))
            report_definition = json_data.get('report')
            data = json_data.get('data')
            is_test_data = bool(json_data.get('isTestData'))
            if not isinstance(report_definition, dict) or not isinstance(data, dict):
                raise_bad_request(reason='report_definition or data missing')
            report = Report(report_definition, data, is_test_data, additional_fonts=self.additional_fonts)
            if report.errors:
                raise_bad_request(reason='error generating report', report_errors=report.errors)

        try:
            # once we have the reportbro.Report instance we can generate
            # the report (pdf or xlsx) and return it
            now = datetime.datetime.now()
            if output_format == 'pdf':
                if report_file is None:
                    # as it is currently implemented the pdf file is always stored in the
                    # report_request table along the other report data. Therefor report_file
                    # will always be set. The generate_pdf call here is only needed in case
                    # the code is changed to clear report_request.pdf_file column when the
                    # data in this table gets too big (currently whole table rows are deleted)
                    report_file = report.generate_pdf()
                self.set_header('Content-Type', 'application/pdf')
                self.set_header('Content-Disposition', 'inline; filename="{filename}"'.format(
                    filename='report-' + str(now) + '.pdf'))
            else:
                report_file = report.generate_xlsx()
                self.set_header('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                self.set_header('Content-Disposition', 'inline; filename="{filename}"'.format(
                    filename='report-' + str(now) + '.xlsx'))
            self.write(bytes(report_file))
        except ReportBroError as exception:
            report_errors = dict(errors=[exception.error])
            raise_bad_request(reason='error generating report', exception=exception, report_errors=report_errors)


class IndexHandler(tornado.web.RequestHandler):
    def get(self):
        self.redirect("/index.html")


def make_app():
    return tornado.web.Application([
        (SERVER_PATH, MainHandler, dict(db_connection=db_connection)),
        ('/?', IndexHandler),
        ('/(.*)', tornado.web.StaticFileHandler, dict(path=BASE_DIR / 'static/'))
    ])


if __name__ == "__main__":
    print(f'Server started and listening {SERVER_PATH}:{SERVER_PORT}')
    app = make_app()
    app.listen(SERVER_PORT)
    tornado.ioloop.IOLoop.current().start()
