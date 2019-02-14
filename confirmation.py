from os import getenv, path
from .settings import get_settings
from base64 import b64encode
from datetime import datetime, date
from decimal import Decimal
import time
from .env import log, clean_html
from urllib.request import quote
from mako.template import Template
import webbrowser


class ArgsWrapper():
    def __init__(self, dict):
        self.dict = dict

    def __getattr__(self, attr):
        if attr in self.dict:
            return self.dict[attr]
        else:
            return None


def handle_remote_confirmation(data):
    code = 1
    error_message = ''

    try:
        bk_no = data['bk_no']
        deposit_requested = 'deposit_amount' in data
        deposit_amount = 0.0
        if deposit_requested:
            deposit_amount = data['deposit_amount']

        body = data['body']
        file_name = data['file_name']
        subject = data['subject']
        destination = data['email']

        fout = f'Z:/Kennels/Confirmations/{file_name}'
        f = open(fout, 'w')
        f.write(body)
        f.close()

        handle_confirmation(bk_no, deposit_amount, subject, fout, 0,
                            destination)
    except Exception as e:
        code = 0
        error_message = str(e)

    return code, error_message


def confirm_all(
        petadmin, report_parameters, action, asofdate=None,
        audit_start=0, additional_text='', forced_subject=''
        ):
    confirmation_candidates = {}
    conf_time = datetime.now()

    env = petadmin.env
    cursor = env.get_cursor()

    # start by adding booking fees as necessary
    sql = 'Execute padd_booking_fee_new'
    env.execute(sql)

    petadmin.load()

    # next read all past emails sent, to safeguard against double-sending

    sql = """
        select hist_bk_no, hist_date, hist_destination, hist_subject
        from vwhistory2
        where hist_report = 'Conf-mail' and hist_type = 'Email Client'
        """
    try:
        cursor.execute(sql)
    except Exception as e:
        log.exception(f"Exception executing '{sql}': {str(e)}")
        return

    past_messages = {}

    for row in cursor:
        bk_no = row[0]
        hist_date = row[1]
        destination = row[2]
        subject = row[3]
        if bk_no not in past_messages:
            past_messages[bk_no] = []
        past_messages[bk_no].append((hist_date, destination, subject))

    if asofdate:
        sql = f"""
        select a.bk_no, aud_type, aud_action, aud_amount, aud_date,
            aud_booking_count, aud_confirm from vwaudit a
        join vwbooking b on a.bk_no = b.bk_no
        where b.bk_start_date > GETDATE() and
            aud_date >= '{asofdate}' order by b.bk_start_date
        """
    elif audit_start > 0:
        sql = """
        select b.bk_no, aud_type, aud_action, aud_amount, aud_date,
            aud_booking_count, aud_confirm from vwaudit_orphan a
        join vwbooking b on a.aud_key = b.bk_no
        where b.bk_start_date > GETDATE() and aud_date >= '{audit_start}'
        order by b.bk_start_date
        """
    else:
        sql = """
        select a.bk_no, aud_type, aud_action, aud_amount, aud_date,
            aud_booking_count, aud_confirm
        from vwrecentaudit a
        join vwbooking b on a.bk_no = b.bk_no
        where b.bk_start_date > GETDATE()
        order by b.bk_start_date
        """

    try:
        cursor.execute(sql)
    except Exception as e:
        log.exception("Exception executing '%s': %s", sql, str(e))
        return

    rows = cursor.fetchall()

    for row in rows:
        bk_no = row[0]
        aud_type = row[1]
        aud_action = row[2]
        aud_amount = row[3]
        aud_date = row[4]
        aud_booking_count = row[5]
        aud_confirm = row[6]

        env.set_key(bk_no, 'B')

        log.debug(
            f'Processing audit event for booking {bk_no}, type {aud_type}'
            f', action {aud_action}'
        )
        if not aud_confirm:
            log.info('Skipping bk_no %d - no confirmation memo' % bk_no)
            continue

        if bk_no in confirmation_candidates:
            cc = confirmation_candidates[bk_no]
        else:
            cc = ConfirmationCandidate(petadmin, bk_no)
            cc.additional_text = additional_text
            cc.forced_subject = forced_subject
            if not cc.booking:
                log.error('Missing booking for bk_no = %d' % bk_no)
                continue

            if cc.booking.status == 'S':
                log.info(
                    f'Skipping booking #{bk_no} '
                    f'- status is {cc.booking.status}'
                )
                continue

            if bk_no in past_messages:
                cc.past_messages = past_messages[bk_no]
            confirmation_candidates[bk_no] = cc
            cc.booking = petadmin.bookings.get(bk_no)

        cc.add_event(aud_type, aud_action, aud_amount, aud_date)
        cc.booking_count = aud_booking_count

    env.clear_key()
    log.info('Confirming %d candidates', len(confirmation_candidates))
    if len(confirmation_candidates) > 0:
        conf_time_str = conf_time.strftime('%Y%m%d %H:%M:%S')
        sql = (f"Insert into tblconfirm (conf_time, conf_candidates) values"
               f"('{conf_time_str}', {len(confirmation_candidates)})")
        try:
            env.execute(sql)
        except Exception as e:
            log.exception("Exception executing '%s': %s", sql, str(e))
            return

        sql = 'Select @@Identity'
        try:
            cursor.execute(sql)
        except Exception as e:
            log.exception("Exception executing '%s': %s", sql, str(e))
            return

        row = cursor.fetchone()
        conf_no = row[0]

        log.debug(
            f'Created confirmation record #{conf_no} with'
            f' {len(confirmation_candidates)} candidates')

        successfuls = 0
        for cc in confirmation_candidates.values():
            env.set_key(cc.booking.no, 'B')
            log.debug('Processing confirmation candidate')
            cc.conf_no = conf_no
            try:
                cc.generate_confirmation(report_parameters, action)
                log.debug('Generate confirmation completed successfully')
                successfuls += 1
            except Exception as e:
                log.exception(
                    f'Exception when generating confirmation for booking '
                    f'{cc.booking.no}: {e}')
        env.clear_key()
        sql = (
            f'Update tblconfirm set conf_successfuls = {successfuls}'
            f' where conf_no = {conf_no}')
        env.execute(sql)

    sql = 'Execute pmaintenance'
    try:
        env.execute(sql)
    except Exception as e:
        log.exception("Exception executing '%s': %s", sql, str(e))
        return


def process_booking(bk_no, args, pa, action, rp, additional_text='',
                    forced_subject=''):
    cc = ConfirmationCandidate(pa, bk_no)
    cc.additional_text = additional_text
    cc.forced_subject = forced_subject
    if args.confirmed:
        cc.booking.status = 'V'
    if args.deposit is not None:
        cc.force_deposit = True
        cc.deposit_amount = Decimal(args.deposit)
    if args.payment is not None:
        cc.payment = True
        cc.payment_amount = Decimal(args.payment)
    if args.amended:
        cc.amended = True
    if args.cancel:
        cc.cancelled = True
    if args.deluxe:
        cc.deluxe = True
    cc.skip = False
    return(cc.generate_confirmation(rp, action))


def handle_confirmation(
        env, bk_no, deposit_amount, subject, file_name,
        conf_no=0, email=''):
    sql = f"Execute pinsert_confaction {conf_no}, {bk_no}, '', '{subject}'" \
          f", '{file_name}', {deposit_amount}, '{email}'"
    env.execute(sql)


class ReportParameters:
    def __init__(self, env):
        self.report = path.join(env.image_folder, "Confirmation.html")
        self.report_txt = path.join(env.image_folder, "Confirmation.txt")
        self.provisional_report = \
            path.join(env.image_folder, "PreBooking.html")
        self.provisional_report_txt = \
            path.join(env.image_folder, "PreBooking.txt")
        self.logo_file = path.join(env.image_folder, "Logo.jpg")
        self.deluxe_logo_file = \
            path.join(env.image_folder, "deluxe_logo_2.png")
        self.pay_deposit_file = path.join(env.image_folder, "paydeposit.png")
        self.logo_code = None
        self.deluxe_logo_code = None
        self.deposit_icon = None
        self.past_messages = []

    # def read_images(self):
    #     with open(self.logo_file, "rb") as f:
    #         data = f.read()
    #         self.logo_code = b64encode(data)

    #     with open(self.deluxe_logo_file, "rb") as f:
    #         data = f.read()
    #         self.deluxe_logo_code = b64encode(data)

    #     with open(self.pay_deposit_file, "rb") as f:
    #         data = f.read()
    #         self.deposit_icon = b64encode(data)

    @staticmethod
    def get_deposit_url(bk_no, deposit_amount, pet_names, customer, expiry=0):
        timestamp = time.mktime(
            datetime.combine(date.today(), datetime.min.time()).timetuple())
        timestamp += expiry * 24 * 3600
        timestamp *= 1000

        url = (
            "https://secure.worldpay.com/wcc/purchase?instId=1094566&"
            f"cartId=PBL-{bk_no}&amount={deposit_amount}&currency=GBP&")
        url += (
            f'desc=Deposit+for+Crowbank+booking+%%23{bk_no}+'
            f'for+{quote(pet_names)}&accId1=CROWBANKPETBM1&testMode=0')
        url += f'&name={quote(customer.display_name())}'
        if customer.email != '':
            url += f'&email={quote(customer.email)}'
        if customer.addr1 != '':
            url += f'&address1={quote(customer.addr1)}'
        if customer.addr2 != '':
            url += f'&address2={quote(customer.addr2)}'
        if customer.addr3 != '':
            url += f'&town={quote(customer.addr3)}'
        if customer.postcode != '':
            url += f'&postcode={quote(customer.postcode)}'
        url += '&country=UK'
        if expiry:
            url += f'`{timestamp}'

        if customer.telno_home != '':
            phone = customer.telno_home
            if len(phone) == 6:
                phone = '01236 ' + phone
            url += '&tel=%s' % quote(phone)

        return url


class ConfirmationCandidate:
    """
    A class representing a candidate for confirmation generation.
    """
    def __init__(self, petadmin, bk_no):
        self.bk_no = bk_no
        # a new booking - any subsequent amendments are 'swallowed'
        self.new = False
        # flag determining whether a payment is acknowledged
        self.payment = False
        # flag determining whether this is an amendment of an existing booking
        self.amended = False
        self.booking = petadmin.bookings.get(bk_no)
        if self.booking:
            self.pet_names = self.booking.pet_names()

        # flag determining whether a deposit request is necessary
        self.deposit = True
        self.deposit_amount = Decimal("0.00")
        self.conf_no = 0
        self.payment_amount = Decimal("0.00")
        self.payment_date = None
        self.title = ''
        self.forced_subject = ''
        self.deluxe = False
        self.env = petadmin.env
        self.booking_count = 0
        self.past_messages = []
        self.force_deposit = False
        self.in_next_year = False
        self.next_years_prices = False
        self.deposit_url = ''
        self.additional_text = ''
        if self.booking:
            self.cancelled = self.booking.status == 'C'
            self.standby = self.booking.status == 'S'
            self.skip = (self.booking.skip == 1)

    def add_event(self, aud_type, aud_action, aud_amount, aud_date):
        if aud_type == 'P' and aud_action == 'A':
            self.payment = True
            self.payment_amount = aud_amount
            self.payment_date = aud_date

        elif aud_type == 'B':
            if aud_action == 'A':
                self.new = True
                self.amended = False
            elif aud_type == 'A' and not self.new:
                self.amended = True
            if aud_action == 'C':
                self.cancelled = True

    def prepare(self, report_parameters=None):
        if not self.booking:
            return

        if self.booking is None:
            raise RuntimeError("Missing booking objects")

        if self.booking.deluxe == 1:
            self.deluxe = True

        if not self.force_deposit:
            if self.standby:
                log.debug('Standby - no deposit')
                self.deposit = False

            if self.deposit and self.booking.status == 'V':
                log.debug('Booking status confirmed - no deposit')
                self.deposit = False

            if self.deposit and self.booking.paid_amt != Decimal("0.00"):
                log.debug('Booking with prior payments - no deposit')
                self.deposit = False

            if self.deposit and self.booking.customer.nodeposit:
                log.debug('Booking with no-deposit customer - no deposit')
                self.deposit = False

            if self.deposit and self.payment_amount != Decimal("0.00"):
                log.debug('Booking associated with payment event - no deposit')
                self.deposit = False

        if self.deposit:
            if self.deposit_amount == Decimal("0.00"):
                self.deposit_amount = Decimal("30.00")
                for pet in self.booking.pets:
                    if pet.spec == 'Dog':
                        self.deposit_amount = Decimal("50.00")
                if self.deposit_amount > self.booking.gross_amt / 2:
                    self.deposit_amount = \
                        Decimal(round(self.booking.gross_amt, 1) / 2)
                    # Round down to nearest 0.05

            if not report_parameters:
                report_parameters = ReportParameters(self.env)

            self.deposit_url = \
                report_parameters.get_deposit_url(
                    self.booking.no, self.deposit_amount,
                    self.booking.pet_names(), self.booking.customer)

        if self.cancelled:
            self.title = 'Booking Cancellation'
        elif self.standby:
            self.title = 'Standby Booking'
        else:
            if self.deposit:
                if self.deluxe:
                    self.title = 'Provisional Deluxe Booking'
                else:
                    self.title = 'Provisional Booking'
            else:
                if self.deluxe:
                    self.title = 'Confirmed Deluxe Booking'
                else:
                    self.title = 'Confirmed Booking'

            if self.amended:
                self.title += ' - Amended'

        self.clean_additional_text = clean_html(self.additional_text)

    def confirmation_body(self, report_parameters=None, body_format='html'):
        if not self.booking:
            return

        self.pet_names = self.booking.pet_names()
        today_date = date.today()

        if not report_parameters:
            report_parameters = ReportParameters(self.env)
#            report_parameters.read_images()

        if body_format == 'html':
            mytemplate = Template(filename=report_parameters.report)
        else:
            mytemplate = Template(filename=report_parameters.report_txt)

        self.paid = self.booking.paid_amt != Decimal(0.00)

        body = mytemplate.render(
            today_date=today_date, conf=self,
            logo_code=report_parameters.logo_code,
            deposit_icon=report_parameters.deposit_icon,
            deluxe_logo_code=report_parameters.deluxe_logo_code,
            deposit_url=self.deposit_url
            )

        return body

    def generate_confirmation(self, report_parameters, action):
        if not self.booking:
            log.error('Missing booking')
            return

        log.debug(
            f'Generating confirmation for booking {self.booking.no}, '
            f'action = {action}'
            )

        if self.skip:
            log.warning(f'Skipping booking {self.booking.no}')
            return

        self.prepare(report_parameters)
        log.info(
            f'Booking {self.booking.no} titled {self.title}.'
            f' Action: {action}')

        body = self.confirmation_body(report_parameters)
        body_txt = self.confirmation_body(report_parameters, body_format='txt')

        now = datetime.now()
        timestamp = now.strftime("%Y%m%d%H%M%S")
        text_file_name = f"{self.booking.no}_{timestamp}.txt"
        fout = path.join(self.env.confirmations_folder, text_file_name)
        f = open(fout, 'w')
        f.write(body_txt)
        f.close()

        file_name = f"{self.booking.no}_{timestamp}.html"
        fout = path.join(self.env.confirmations_folder, file_name)
        f = open(fout, 'w')
        f.write(body)
        f.close()

        send_email = False
        if action == 'email':
            send_email = True

        if action == 'display' or action == 'review':
            webbrowser.open_new_tab(fout)

        if action == 'review':
            response = input("Email message [Y/N]? ")
            send_email = (response.lower()[0] == 'y')

        if send_email:
            if self.booking.customer.email == '':
                log.warning(
                    f'Customer {self.booking.customer.no} '
                    f'({self.booking.customer.surname})'
                    f' has no email address [bk_no={self.booking.no}]'
                    )
            else:
                if self.forced_subject:
                    subject = self.forced_subject
                else:
                    subject = f'{self.title} #{self.booking.no}'

                self.env.send_email(
                    self.booking.customer.email, body,
                    subject, body_txt
                    )

                try:
                    if not self.deposit:
                        self.deposit_amount = 0.0
                    handle_confirmation(
                        self.env, self.booking.no, self.deposit_amount,
                        subject, file_name, self.conf_no,
                        self.booking.customer.email
                        )
                except Exception as e:
                    log.exception(str(e))

        log.debug('Confirmation complete')
        return (file_name, text_file_name)
