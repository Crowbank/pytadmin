from .env import log


class Customers:
    def __init__(self, env):
        self.customers = {}
        self.env = env
        self.loaded = False

    def get(self, cust_no):
        if cust_no in self.customers:
            return self.customers[cust_no]
        else:
            return None

    def load_by_sql(self, sql):
        cursor = self.env.get_cursor()

        cursor.execute(sql)
        for row in cursor:
            cust_no = row[0]
            customer = Customer(cust_no)
            customer.surname = row[1]
            customer.forename = row[2]
            customer.addr1 = row[3]
            customer.addr2 = row[4]
            customer.addr3 = row[5]
            customer.postcode = row[6]
            customer.telno_home = row[7]
            customer.email = row[8]
            customer.discount = row[9]
            customer.telno_mobile = row[10]
            customer.title = row[11]
            customer.nodeposit = row[12]
            customer.deposit_requested = row[13]
            customer.nosms = row[14]

            self.customers[cust_no] = customer

    def load(self, force=False):
        if self.loaded and not force:
            return

        log.debug('Loading Customers')

        sql = (
            "Select cust_no, cust_surname, cust_forename, cust_addr1, "
            "cust_addr2, cust_addr3, cust_postcode, cust_telno_home, "
            "cust_email, cust_discount, cust_telno_mobile, cust_title, "
            "cust_nodeposit, cust_deposit_requested, cust_nosms "
            "from vwcustomer"
        )

        self.load_by_sql(sql)

        log.debug(f'Loaded {len(self.customers)} customers')
        self.loaded = True

    def load_one(self, cust_no):
        if self.loaded or cust_no in self.customers:
            return

        log.debug(f'Loading customer #{cust_no}')

        sql = (
            "Select cust_no, cust_surname, cust_forename, "
            "cust_addr1, cust_addr2, cust_addr3, cust_postcode, "
            "cust_telno_home, cust_email, cust_discount, "
            "cust_telno_mobile, cust_title, cust_nodeposit, "
            "cust_deposit_requested, cust_nosms "
            f"from vwcustomer where cust_no = {cust_no}")

        self.load_by_sql(sql)

        log.debug(f'Loaded customer {cust_no}')


class Customer:
    """Representing a PetAdmin Customer"""

    def __init__(self, cust_no):
        self.no = cust_no
        self.pets = []
        self.surname = ''
        self.forename = ''
        self.addr1 = ''
        self.addr2 = ''
        self.addr3 = ''
        self.postcode = ''
        self.telno_home = ''
        self.email = ''
        self.discount = 0.0
        self.telno_mobile = ''
        self.title = ''
        self.nodeposit = 0
        self.deposit_requested = 0
        self.notes = ''

    def add_pet(self, pet):
        self.pets.append(pet)

    def display_name(self):
        if self.title == '':
            display_name = ''
        else:
            display_name = self.title + ' '

        if self.forename != '':
            display_name += ' ' + self.forename

        if display_name != '':
            display_name += ' '

        display_name += self.surname

        return display_name

    def full_address(self):
        full_address = self.display_name()
        if self.addr1 != '':
            full_address += '\n' + self.addr1
        if self.addr2 != '':
            full_address += '\n' + self.addr2
        if self.postcode != '':
            full_address += '\n' + self.postcode

        return full_address

    def write(self, env):
        sql = \
            f"execute pcreate_customer '{self.surname}', '{self.forename}', " \
            f"'{self.addr1}', '{self.addr3}', '{self.postcode}', " \
            f"'{self.telno_home}', '{self.telno_mobile}', '{self.email}', " \
            f"'{self.notes}'"

        env.execute(sql)
