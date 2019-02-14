from .env import log

class Breeds:
    """Representing a collection of breeds"""

    def __init__(self, env):
        self.breeds = {}
        self.env = env
        self.loaded = False

    def get(self, breed_no):
        if breed_no in self.breeds:
            return self.breeds[breed_no]
        else:
            return None

    def load(self, force=False):
        if self.loaded and not force:
            return

        log.debug('Loading Breeds')

        cursor = self.env.get_cursor()
        sql = 'select breed_no, breed_desc, spec_desc, billcat_desc from vwbreed'

        cursor.execute(sql)
        for row in cursor:
            breed_no = row[0]
            breed = Breed(breed_no)
            self.breeds[breed_no] = breed
            breed.desc = row[1]
            breed.spec = row[2]
            breed.bill_category = row[3]

        self.loaded = True


class Breed:
    """Representing a particular breed"""

    def __init__(self, breed_no):
        self.no = breed_no
        self.desc = ''
        self.spec = ''
        self.bill_category = ''

    def __str__(self):
        return self.desc
