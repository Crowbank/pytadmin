from .env import log
from .customer import Customers
from .breed import Breeds
from .pet import Pets
from .service import Services
from .booking import Bookings
from .run import Runs

class PetAdmin:
    def __init__(self, env):
        self.env = env
        self.customers = Customers(env)
        self.breeds = Breeds(env)
        self.pets = Pets(env, self.customers, self.breeds)
        self.services = Services(env)
        self.bookings = Bookings(env, self.customers, self.pets, self.services)
        self.runs = Runs(env, self.bookings, self.pets)
        self.loaded = False

    def load(self, force=False):
        if self.loaded and not force:
            return

        log.debug('Loading PetAdmin')
        self.customers.load(force)
        self.pets.load(force)
        self.services.load(force)
        self.bookings.load(force)
        self.runs.load(force)

        self.loaded = True
        log.debug('Loading PetAdmin Complete')
    
    def load_customer(self, cust_no):
        if self.loaded:
            return
        
        log.debug(f'Loading customer #{cust_no}')
        self.services.load()
        self.customers.load_one(cust_no)
        self.pets.load_for_customer(cust_no)
        self.bookings.load_for_customer(cust_no)