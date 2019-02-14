import sys
import pymssql
# if sys.platform == 'cygwin':
#     import pyodbc
import smtplib
import logging
import logging.handlers
import re
from os import getenv

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from datetime import datetime
from pypa.settings import get_settings

assert(sys.platform == 'win32')

log = logging.getLogger(__name__)

ENVIRONMENT = getenv("DJANGO_ENVIRONMENT")
if not ENVIRONMENT:
    ENVIRONMENT = 'prod'


TAG_RE = re.compile(r'<[^>]+>')


def clean_html(html_text: str) -> str:
    return TAG_RE.sub('', html_text)


class DatabaseHandler(logging.Handler):
    def __init__(self, env):
        logging.Handler.__init__(self)
        self.env = env

    def emit(self, record):
        msg = self.format(record)
        levelname = record.levelname
        filename = record.filename
        lineno = record.lineno
        sql = f"""
Execute plog '{msg.replace("'", "''")}', '{levelname}', '{self.env.context}',
{self.env.key}, '{self.env.key_type}',
'{filename}', {lineno}"""

        self.env.execute(sql)


class BufferingSMTPHandler(logging.handlers.BufferingHandler):
    def __init__(self, env):
        logging.handlers.BufferingHandler.__init__(self, 1000)
        self.env = env
        self.mailhost = env.email_host
        self.mailport = None
        self.fromaddr = env.email_user
        self.toaddrs = env.email_logs
        self.subject = 'Python Log'
        self.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(message)s"))

    def flush(self):
        if len(self.buffer) > 0:
            try:
                body = ''
                for record in self.buffer:
                    s = self.format(record)
                    body += s + "<br/>"

                self.env.send_email(
                    self.toaddrs, body, self.subject, body, True)
            except Exception:
                self.handleError(None)  # no particular record
            self.buffer = []


class Environment:
    def __init__(self, context, env_type=''):
        if env_type:
            ENVIRONMENT = env_type
        else:
            ENVIRONMENT = getenv("DJANGO_ENVIRONMENT")
            if ENVIRONMENT:
                env_type = ENVIRONMENT
            else:
                env_type = 'prod'

        self.settings = get_settings(env_type)
        self.env_type = env_type
        self.platform = sys.platform

        self.smtp_server = None
        self.connection = None
        self.is_test = (env_type != 'prod')
        self.smtp_handler = None
        self.context = context
        self.key = 0
        self.key_type = ''

    def __getattr__(self, attr):
        if attr in self.settings:
            return self.settings[attr]

        uattr = attr.upper()
        if uattr in self.settings:
            return self.settings[uattr]

        raise AttributeError

    def set_key(self, key, key_type):
        self.key = key
        self.key_type = key_type

    def clear_key(self):
        self.key = 0
        self.key_type = ''

    def get_smtp_server(self):
        if self.smtp_server:
            if self.smtp_server.noop()[0] == 250:
                return self.smtp_server
            self.smtp_server.connect(self.email_host)
        else:
            self.smtp_server = smtplib.SMTP_SSL(
                self.email_host, 465, timeout=120)
        self.smtp_server.ehlo()
        self.smtp_server.login(self.email_user, self.email_pwd)

        return self.smtp_server

    def configure_logger(self, logger):
        file_handler = logging.handlers.TimedRotatingFileHandler(
            self.log_file, when='W0')

        debug = (self.env_type in ('qa', 'dev'))

        self.smtp_handler = BufferingSMTPHandler(self)
        stream_handler = logging.StreamHandler()
        if not self.smtp_server:
            try:
                self.get_smtp_server()
            except Exception:
                logger.error('Unable to connect to smtp server')

        formatter = logging.Formatter(
            '%(asctime)s  [%(levelname)-5s] %(message)s')
        file_handler.setFormatter(formatter)
        stream_handler.setFormatter(formatter)
        self.smtp_handler.setFormatter(formatter)

        db_handler = DatabaseHandler(self)

        logger.addHandler(file_handler)
        logger.addHandler(self.smtp_handler)
        logger.addHandler(stream_handler)
        logger.addHandler(db_handler)

        if self.is_test or debug:
            logger.setLevel(logging.DEBUG)
            self.smtp_handler.setLevel(logging.INFO)
        else:
            logger.setLevel(logging.INFO)
            self.smtp_handler.setLevel(logging.WARNING)

    def get_connection(self):
        if not self.connection:
            # if self.platform == 'win32':
            self.connection = pymssql.connect(
                server=self.db_server, user=self.db_user, password=self.db_pwd,
                database=self.db_database)
            #             else:
            #                 driver = 'SQL SERVER'
            #                 self.connection = pyodbc.connect(
            # f"""DRIVER={driver};SERVER={self.db_server};DATABASE={self.db_database};
            # UID={self.db_user};PWD={self.db_pwd}"""
            #                     )

        return self.connection

    def get_cursor(self):
        conn = self.get_connection()
        cur = conn.cursor()
        return cur

    def execute(self, sql, commit=None):
        if commit is None:
            commit = not self.is_test
        conn = self.get_connection()
        cur = conn.cursor()
        try:
            cur.execute(sql)
            if commit:
                conn.commit()
        except Exception as e:
            log.error(f'Error executing {sql}: {e}')

    def check_exists(self, sql):
        sql_wrapper = f"if exists ({sql}) select 1 else select 0"
        cur = self.get_cursor()
        cur.execute(sql_wrapper)
        res = cur.fetchone()[0]
        return(res == 1)

    def get_server(self):
        cur = self.get_cursor()
        sql = 'select @@servername'
        cur.execute(sql)
        for row in cur:
            return row[0]

    def send_email(
        self, send_to, send_body, send_subject, alt_body, force_send=False
    ):
        msg = MIMEMultipart('alternative')

        if self.env_type != "prod":
            send_subject += f' ({ENVIRONMENT})'
            send_to = self.email_bcc

        msg['Subject'] = send_subject
        msg['From'] = self.email_user
        msg['To'] = send_to
        msg['Date'] = formatdate(localtime=True)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        msg['Message-Id'] = f'{timestamp}@crowbank.co.uk'

        part1 = MIMEText(alt_body, 'plain')
        part2 = MIMEText(send_body, 'html')

        msg.attach(part1)
        msg.attach(part2)

        try:
            server = self.get_smtp_server()
            server.sendmail(self.email_user, [send_to], msg.as_string())
        except smtplib.SMTPServerDisconnected:
            self.smtp_server.connect()
            server.sendmail(self.email_user, [send_to], msg.as_string())

    def send_email_old(
            self, send_to, send_body, send_subject, force_send=False):
        target = [send_to]
        if ENVIRONMENT != "prod":
            send_subject += f' ({ENVIRONMENT})'
            target = [self.email_bcc]
        msg = f"""
To:{send_to}\nMIME-Version: 1.0\nContent-type: text/html\n
From: Crowbank Kennels and Cattery <{self.email_user}>\n
Subject:{send_subject}\n
\n
{send_body}"""

        try:
            server = self.get_smtp_server()
            server.sendmail(self.email_user, target, msg)
        except smtplib.SMTPServerDisconnected:
            self.smtp_server.connect()
            self.smtp_server.sendmail(self.email_user, target, msg)

    def close(self):
        if self.connection:
            self.connection.close()
        if self.smtp_handler:
            self.smtp_handler.flush()
