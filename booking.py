from decimal import Decimal

class Bookings:
    """Representing a collection of Booking objects
    """

    def __init__(self, env, customers, pets, services):
        self.bookings = {}
        self.by_start_date = {}
        self.env = env
        self.loaded = False
        self.customers = customers
        self.pets = pets
        self.services = services

    def get(self, bk_no):
        if bk_no in self.bookings:
            return self.bookings[bk_no]
        else:
            return None

    def get_by_start_date(self, start_date):
        self.load()
        if start_date in self.by_start_date:
            return self.by_start_date[start_date]
        
        return []
        
    def load_by_sql(self, sql_booking, sql_bookingitem, sql_invitem,
            sql_invextra, sql_payment):
        cursor = self.env.get_cursor()
        cursor.execute(sql_booking)

        for row in cursor:
            bk_no = row[0]
            booking = Booking(bk_no)
            cust_no = row[1]
            booking.customer = self.customers.get(cust_no)
            booking.create_date = row[2]
            booking.start_date = row[3]
            booking.end_date = row[4]
            booking.gross_amt = row[5]
            booking.paid_amt = row[6]
            booking.status = row[7]
            booking.peak = row[8]
            booking.deluxe = row[9]
            booking.skip = row[10]
            booking.pickup = row[11]
            self.bookings[bk_no] = booking
            sdate = booking.start_date.date()
            if booking.status == '' or booking.status == 'V':
                if sdate in self.by_start_date:
                    self.by_start_date[sdate].append(booking)
                else:
                    self.by_start_date[sdate] = [booking]

        cursor.execute(sql_bookingitem)

        for row in cursor:
            booking = self.get(row[0])
            pet = self.pets.get(row[1])
            if not booking:
                pass
            else:
                booking.pets.append(pet)

        cursor.execute(sql_invitem)

        for row in cursor:
            booking = self.get(row[0])
            if booking:
                pet = self.pets.get(row[1])
                service = self.services.get(row[2])
                inv_item = InventoryItem(pet, service, row[3], row[4])
                booking.inv_items.append(inv_item)

        cursor.execute(sql_invextra)

        for row in cursor:
            booking = self.get(row[0])
            if booking:
                desc = row[1]
                unit_price = row[2]
                quantity = row[3]
                extra_item = ExtraItem(desc, unit_price, quantity)
                booking.extra_items.append(extra_item)

        cursor.execute(sql_payment)

        for row in cursor:
            booking = self.get(row[0])
            pay_date = row[1]
            amount = row[2]
            pay_type = row[3]
            payment = Payment(pay_date, amount, pay_type)
            booking.payments.append(payment)


    def load(self, force=False):
        if self.loaded and not force:
            return

        log.debug('Loading Bookings')

        sql_booking = """
Select bk_no, bk_cust_no, bk_create_date, bk_start_datetime, bk_end_datetime,
bk_gross_amt, bk_paid_amt, bk_status, bk_peak, bk_deluxe, bk_skip_confirm,
bk_pickup_no from vwbooking"""
        sql_bookingitem = """
Select bi_bk_no, bi_pet_no from vwbookingitem_simple"""
        sql_invitem = """
Select ii_bk_no, ii_pet_no, ii_srv_no, ii_quantity, ii_rate from vwinvitem"""
        sql_invextra = """
Select ie_bk_no, ie_desc, ie_unit_price, ie_quantity from vwinvextra"""
        sql_payment = """
Select pay_bk_no, pay_date, pay_amount, pay_type from vwpayment_simple"""

        self.load_by_sql(sql_booking, sql_bookingitem, sql_invitem, sql_invextra,
            sql_payment)

        log.debug(f'Loaded {len(self.bookings)} bookings')
        self.loaded = True


    def load_for_customer(self, cust_no):
        if self.loaded:
            return

        log.debug(f'Loading Bookings for customer #{cust_no}')
        sql_booking = f"""
Select bk_no, bk_cust_no, bk_create_date, bk_start_datetime, bk_end_datetime,
bk_gross_amt, bk_paid_amt, bk_status, bk_peak, bk_deluxe, bk_skip_confirm,
bk_pickup_no from vwbooking
where bk_cust_no = {cust_no}"""
        sql_bookingitem = f"""
Select bi_bk_no, bi_pet_no
from vwbookingitem_simple
where bi_cust_no = {cust_no}"""
        sql_invitem = f"""
Select ii_bk_no, ii_pet_no, ii_srv_no, ii_quantity, ii_rate
from vwinvitem where ii_cust_no = {cust_no}"""
        sql_invextra = f"""
Select ie_bk_no, ie_desc, ie_unit_price, ie_quantity
from vwinvextra
where ie_cust_no = {cust_no}"""
        sql_payment = f"""
Select pay_bk_no, pay_date, pay_amount, pay_type
from vwpayment_simple where pay_cust_no = {cust_no}"""

        self.load_by_sql(sql_booking, sql_bookingitem, sql_invitem, sql_invextra,
            sql_payment)

        log.debug(f'Loaded bookings for customer #{cust_no}')
        self.loaded = True


class Payment:
    def __init__(self, pay_date, amount, pay_type):
        self.pay_date = pay_date
        self.amount = amount
        self.type = pay_type


from .env import log

class ExtraItem:
    def __init__(self, desc, unit_price, quantity):
        self.desc = desc
        self.unit_price = unit_price
        self.quantity = quantity


class InventoryItem:
    def __init__(self, pet, service, quantity, rate):
        self.pet = pet
        self.service = service
        self.quantity = quantity
        self.rate = rate


class Booking:
    """Representing a PetAdmin Booking"""

    def __init__(self, bk_no):
        self.no = bk_no
        self.customer = None
        self.pets = []
        self.create_date = None
        self.start_date = None
        self.end_date = None
        self.status = ''
        self.skip = 0
        self.gross_amt = Decimal("0.0")
        self.paid_amt = Decimal("0.0")
        self.inv_items = []
        self.extra_items = []
        self.payments = []
        self.peak = 0
        self.deluxe = 0
        self.skip = 0

    def pet_names(self):
        if len(self.pets) == 1:
            return self.pets[0].name
        return ', '.join(map(lambda p: p.name, self.pets[0:-1])) + \
            ' and ' + self.pets[-1].name

    def add_payment(self, payment):
        self.payments.append(payment)

    def outstanding_amt(self):
        return self.gross_amt - self.paid_amt
