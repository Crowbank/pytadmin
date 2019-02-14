from .env import log


class Services:
    """Representing a collection of PetAdmin services"""

    def __init__(self, env):
        self.env = env
        self.services = {}
        self.loaded = False

    def get(self, srv_no):
        if srv_no in self.services:
            return self.services[srv_no]
        else:
            return None

    def load(self, force=False):
        if self.loaded and not force:
            return

        sql = 'Select srv_no, srv_desc, srv_code from vwservice'
        cursor = self.env.get_cursor()
        cursor.execute(sql)

        for row in cursor:
            srv_no = row[0]
            service = Service(srv_no, row[1], row[2])
            self.services[srv_no] = service

        self.loaded = True


class Service:
    """Representing a PetAdmin service"""

    def __init__(self, srv_no, desc, code):
        self.srv_no = srv_no
        self.code = code
        self.desc = desc
