from .env import log
from datetime import date, timedelta

class Runs:
    """
    Representing the collection of all runs in the kennels
    """

    def __init__(self, env, bookings, pets):
        self.runs = {}
        self.env = env
        self.runs_by_type = {}
        self.bookings = bookings
        self.pets = pets
        self.potential_vacancies = {}
        self.vacancies = {}
        self.min_date = date(2099, 12, 31)
        self.max_date = date(1970, 1, 1)
        self.loaded = False
        
    def load(self, force=False):
        if self.loaded and not force:
            return

        sql = "select run_no, run_code, spec_desc, rt_desc from vwrun"
        cursor = self.env.get_cursor()
        cursor.execute(sql)

        for row in cursor:
            run = Run()
            run.no = row[0]
            run.code = row[1]
            run.spec = row[2]
            run.type = row[3]
            self.runs[run.no] = run
            if run.spec not in self.runs_by_type:
                self.runs_by_type[run.spec] = {}

            if run.type not in self.runs_by_type[run.spec]:
                self.runs_by_type[run.spec][run.type] = []

            self.runs_by_type[run.spec][run.type].append(run)
            if not (run.spec, run.type) in self.potential_vacancies:
                self.potential_vacancies[(run.spec, run.type)] = 0
            self.potential_vacancies[(run.spec, run.type)] += 1

        sql = """
select ro_run_no, ro_pet_no, ro_date, ro_bk_no, ro_type from vwrunoccupancy"""
        cursor.execute(sql)

        for row in cursor:
            run = self.runs[row[0]]
            pet = self.pets.get(row[1])
            ro_date = row[2].date()
            booking = self.bookings.get(row[3])
            ro_type = row[4]
            run.add_occupancy(booking, pet, ro_date, ro_type)
            if ro_date < self.min_date:
                self.min_date = ro_date
            if ro_date > self.max_date:
                self.max_date = ro_date

        ro_date = self.min_date
        one_day = timedelta(days=1)
        while ro_date <= self.max_date:
            self.vacancies[ro_date] = {}
            for spec in self.runs_by_type.keys():
                for run_type in self.runs_by_type[spec].keys():
                    self.vacancies[ro_date][(spec, run_type)] = \
                        self.potential_vacancies[(spec, run_type)]
                    for run in self.runs_by_type[spec][run_type]:
                        if ro_date in run.occupancy:
                            self.vacancies[ro_date][(spec, run_type)] -= 1
            ro_date += one_day

        self.loaded = True

    def check_availability(self, from_date, to_date, spec, run_type, run_count=1):
        """
        Check to see whether we have availability in a given type of run.
        A run is considered available only if no pet is assigned to each at
        any time during the day.
        Thus the test may fail while there is still room to accommodate leavers
        and arrivers in the same run
        :param from_date:   first date to be checked, typically bk_start_date
        :param to_date:     last date to be checked, typically bk_end_date
        :param spec:        species, 'Cat' or 'Dog'
        :param run_type:    run type, e.g. 'standard', 'double' or 'deluxe'
                            for dogs
        :param run_count: Number of runs required (default to 1)
        :return:
        """

        one_day = timedelta(days=1)
        ro_date = from_date
        while ro_date <= to_date:
            if self.vacancies[ro_date][[spec, run_type]] < run_count:
                return False
            ro_date += one_day

        return True

    def allocate_booking(self, booking, run_type=None, pets=None, start_date=None,
        stay_length=0):
        """
        :param booking: booking to be allocated into runs
        :param run_type: type of run to be used for dogs.
            All cats are assumed to use standard run.
        :param pets: a list of pets to be allocated.
            If None, all pets of each spec are co-habiting
        :param start_date: first date to be allocated.
            defaults to booking.start_date
        :param stay_length: number of days to be allocated.
            defaults to length of booking
        :return: True for success, False for failure
        """

        if pets is None:
            pets = booking.pets

        for spec in ['Cat', 'Dog']:
            spec_pets = filter(lambda p: p.spec == spec, pets)
            if spec_pets:
                if spec == 'Cat' or run_type is None:
                    spec_run_type = 'Standard'
                else:
                    spec_run_type = run_type

                if not stay_length:
                    stay_length = (booking.end_date - booking.start_date).days + 1

                if not start_date:
                    start_date = booking.start_date

                run = max(self.runs_by_type[spec][spec_run_type],
                          key=lambda r: r.free_length(start_date, stay_length))

                move_list = []
                run.add_occupancy_range(booking, spec_pets, booking.start_date,
                    stay_length, move_list)
                while move_list:
                    to_move = move_list.pop(0)
                    self.allocate_booking(to_move[0][0], run.run_type,
                        to_move[0][1], to_move[1], to_move[2])


class Run:
    """
    Representing a dog kennel or cat pen
    """

    def __init__(self):
        self.no = -1
        self.code = ''
        self.occupancy = {}
        self.spec = ''
        self.type = ''

    def add_occupancy(self, booking, pet, ro_date, ro_type=None):
        if ro_date not in self.occupancy:
            self.occupancy[ro_date] = {}

        if booking.no not in self.occupancy[ro_date]:
            self.occupancy[ro_date][booking.no] = [booking, [pet], ro_type]
        else:
            self.occupancy[ro_date][booking.no][1].append(pet)

    def free_length(self, ro_date, ro_length):
        if ro_date in self.occupancy:
            return 0

        i = 0

        for i in range(ro_length):
            if ro_date + timedelta(days=i) in self.occupancy:
                break

        return i

    def same_length(self, current_date, bk_no):
        current_set = self.occupancy[current_date][bk_no]
        i = 1
        while bk_no in self.occupancy[current_date + timedelta(days=i)]\
             and self.occupancy[current_date + timedelta(days=i)][1] ==\
              current_set[1]:
            i += 1

        return i

    def clear_run(self, start_date, bk_no, stay_length):
        for i in range(stay_length):
            del self.occupancy[start_date + timedelta(days=i)][bk_no]

    def add_occupancy_range(self, booking, pets, from_date, day_count, reject_list):
        for i in range(day_count):
            current_date = from_date + timedelta(days=i)
            if current_date in self.occupancy:
                for bk_no in self.occupancy[current_date]:
                    stay_length = self.same_length(current_date, bk_no)
                    reject_list.append((self.occupancy[current_date], \
                    current_date, stay_length))
                    self.clear_run(current_date, bk_no, stay_length)
            for pet in pets:
                self.add_occupancy(booking, pet, current_date)
