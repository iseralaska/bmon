'''Runs periodic scripts that are set up in the Django Admin for this
instance of BMON.  Often, these scripts collect reading values and insert
them into the reading database.
This script is usually run via a cron job every five minutes.

This script is set up to run through use of the django-extensions runscript
feature, in order that the script has easy access to the Django model data
for this application.  The script is run by:

    manage.py runscript run_periodic_scripts

This script is also called from the main_cron.py script.
'''

import logging
import threading
import time
import random
import importlib
import yaml
from bmsapp.readingdb import bmsdata
import bmsapp.models

CRON_PERIOD = 300

def run():
    '''This method is called by the 'runscript' command and is the entry point for
    this module.
    '''

    # make a logger object
    logger = logging.getLogger('bms.run_periodic_scripts')


class RunScript(threading.Thread):
    '''
    This class will run one periodic script in a separate thread.
    '''

    def __init__(self, script, cron_time=time.time()):
        """
        :param script: the models.PeriodicScript object containing info about the
            script to run.
        :param cron_time:  the UNIX epoch timestamp of the time when this batch of
            scripts was initiated.  This time is used to determine whether it is the
            proper time to run the script.
        """
        threading.Thread.__init__(self)
        self.script = script
        self.cron_time = cron_time

    def run(self):
        """This function is run in a new thread and runs the desired script if the time is correct
        """

        if (self.cron_time % self.script.period) >= CRON_PERIOD:
            # Not the correct time to run script, so exit.
            return

        # in order to minimize coincident requests on resources due to multiple scripts
        # starting at the same time, introduce a random delay, up to 10 seconds.
        time.sleep(random.random() * 10.0)

        # Assemble the paramater list to pass to the script.  It consists of the
        # combination of the configuration parameters and saved results from the
        # last run of the script.
        params = yaml.load(self.script.script_parameters)
        params.update(self.script.script_results)

        # import the periodic script module, but first strip off any extension that
        # the user may have appended
        script_mod_base = self.script.script_file_name.split('.')[0]
        script_mod = importlib.import_module('bmsapp.periodic_scripts.' + script_mod_base)

        # The script is coded in the 'run' function, so run it with the input parameters.
        # Capture the output.
        results = script_mod.run(params)

        # if the results contains a 'readings' key, then extract those readings for
        # storage into the reading database.
        if 'readings' in results:
            sensor_reads = results.pop('readings')
            if len(sensor_reads):
                # change the shape of the sensor readings into separate lists,
                # which is what the "insert_reading" function call needs.
                ts, ids, vals = zip(*sensor_reads)

                # get a connection to the reading database and insert
                reading_db = bmsdata.BMSdata()
                insert_msg = reading_db.insert_reading(ts, ids, vals)
                # store this message so it can be seen in the Django Admin
                # interface
                results['reading_insert_message'] = insert_msg
                # **** DO WE WANT TO LOG THIS AS WELL?


        # Store the results back into the model script object so they are available
        # for the next call.
        self.script.script_results = results
        self.script.script_results.save()



