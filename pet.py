from .env import log
from datetime import date

class Pets:
    """Representing a collection of Pets"""

    def __init__(self, env, customers=None, breeds=None):
        self.pets = {}
        self.env = env
        self.loaded = False
        self.customers = customers
        self.breeds = breeds

    def get(self, pet_no):
        if pet_no in self.pets:
            return self.pets[pet_no]
        else:
            return None

    def load_by_sql(self, sql):
        cursor = self.env.get_cursor()

        cursor.execute(sql)
        for row in cursor:
            pet_no = row[0]
            pet = Pet(pet_no)
            cust_no = row[1]
            if self.customers is not None:
                customer = self.customers.get(cust_no)
                if not customer:
                    log.error(f'Missing customer for pet #{pet_no}')
                    next()
                pet.customer = customer
                customer.add_pet(pet)
            pet.name = row[2]
            breed_no = row[3]
            if self.breeds is not None:
                breed = self.breeds.get(breed_no)
                if not breed:
                    log.error(f'Missing breed for pet #{pet_no}')
                    next()
            pet.breed = breed
            pet.spec = row[4]
            pet.dob = row[5]
            pet.sex = row[6]
            pet.vacc_status = row[7]
            self.pets[pet_no] = pet

    def load_for_customer(self, cust_no):
        if self.loaded:
            return

        log.debug(f'Loading Pets for customer #{cust_no}')

        if self.customers is not None and cust_no not in self.customers.customers:
            self.customers.load_one(cust_no)
        if self.breeds is not None:
            self.breeds.load()

        sql = f"""
select pet_no, cust_no, pet_name, breed_no, spec_desc, pet_dob, pet_sex,
pet_vacc_status from vwpet where cust_no = {cust_no}"""
        self.load_by_sql(sql)

        log.debug('Loaded %d pets', len(self.pets))
        self.loaded = True
        

    def load(self, force=False):
        if self.loaded and not force:
            return

        log.debug('Loading Pets')
        if self.customers is not None:
            self.customers.load()
        if self.breeds is not None:
            self.breeds.load()

        sql = """select pet_no, cust_no, pet_name, breed_no, spec_desc, pet_dob,
pet_sex, pet_vacc_status from vwpet"""
        self.load_by_sql(sql)

        log.debug(f'Loaded {len(self.pets)} pets')
        self.loaded = True


class Pet:
    """Reoresenting a PetAdmin Pet"""

    def __init__(self, pet_no):
        self.no = pet_no
        self.name = ''
        self.customer = None
        self.breed = None
        self.sex = ''
        self.spec = ''
        self.dob = date.today()

    def __str__(self):
        return self.name
