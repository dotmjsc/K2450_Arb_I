"""
Keithley 2450 sequenced current source
written by markus(a)schrodt.at
LICENSE: GPL-3.0-or-later
"""

import pyvisa
import logging
import time
import numpy as np
from K2450_Config import K2450_Config


def get_visa_devices():
    rm = pyvisa.ResourceManager()
    devices = rm.list_resources()
    rm.close()
    return devices


class K2450_ArbCurrentSource(object):

    def __init__(self, address):
        self._address = address
        self._rm = pyvisa.ResourceManager()
        self._inst = None

        devices = self._rm.list_resources()

        logging.info('K2450: try to open %s' % address)
        if self._address not in devices:
            logging.error('K2450: VISA device not found')
            raise RuntimeError
        try:
            self._inst = self._rm.open_resource(self._address)
            self._inst.write("*IDN?\n")
            visa_answer = self._inst.read()
            if "KEITHLEY" and "2450" in visa_answer:
                logging.info("K2450: Successfully opened: " + visa_answer)

                # default settings, OFFMODE is essential!
                self._inst.write("smu.source.level = 0")
                self._inst.write("smu.source.offmode = smu.OFFMODE_HIGHZ")
                self._inst.write("smu.source.output = smu.OFF")
                logging.info("K2450: SMU set to High-Z and Output OFF")
            else:
                logging.error('K2450: Keithley 2450 not found in answer: ' + visa_answer)
                raise RuntimeError
        except:
            logging.error('K2450: Visa resource open unsuccessful')
            raise RuntimeError

        self.config = K2450_Config()
        self._datapoints = []
        self._result_voltages = []
        self._result_timestamps = []
        self._result_currents = []
        self._run_warnings = 0
        self._linefreq = self.get_linefreq()
        logging.info('K2450: Line frequency: %d' % self._linefreq)  # necessary for nplc calculation

    def __del__(self):
        self._rm.close()

    def _calc_timing(self, my_source_range):
        """
        calculates the essential sourcing / measuring timings
        :param my_source_range: the actual current source range
        :return: max_measure time: the maximum time for the measuring block
                 source_delay: the total delay between sourcing and measuring
        """
        current_source_ranges = [10e-9, 100e-9, 1e-6, 10e-6, 100e-6, 1e-3, 10e-3, 100e-3, 1]
        autodelays = [50e-3, 50e-3, 3e-3, 2e-3, 1e-3, 1e-3, 1e-3, 1e-3, 2e-3]
        trigger_latency = 120e-6

        # case autodelay
        if self.config.auto_delay is True:
            autodelay_found = False
            for i, source_range in enumerate(current_source_ranges):
                if source_range == my_source_range:
                    autodelay_found = autodelays[i]
                    logging.info('K2450 Timing: Current source autodelay is %0.2f ms' % (autodelay_found * 1000))

            if autodelay_found is False:
                logging.error('K2450 Timing: No valid range found for autodelay lookup')
                return False, False

            source_delay = (autodelay_found + trigger_latency)

        # case manual delay
        else:
            source_delay = (self.config.manual_delay + trigger_latency)

        # double measure time if autozero is used (i think so?)
        if self.config.auto_zero is False:
            available_time = self.config.time_step
        else:
            available_time = self.config.time_step/2

        max_measure_time = available_time - source_delay
        logging.info('K2450 Timing: Maximum time for a measurement is: %0.2f ms' % (max_measure_time * 1000))

        return max_measure_time, source_delay

    def _calc_autonplc(self, max_measure_time):
        """
        calculate nplc setting based on the time the SMU got for the actual measuring
        :param max_measure_time: from _calc_timing
        :return: the suggested maximum nplc setting
        """
        max_measure_time = max_measure_time * 0.95  # safety factor

        one_nplc = 1/self._linefreq
        nplc_found = max_measure_time/one_nplc
        if nplc_found < (one_nplc*0.01):  # the smallest setting is 0.01!
            nplc_found = 0.01
            logging.warning('K2450 Auto NPLC: NPLC underrange -> set to 0.01! Check timestep and autodelay settings!')
            self._run_warnings += 1
        else:
            logging.info('K2450 Auto NPLC: NPLC set to %0.2f' % nplc_found)

        # nplc must definitely be floored when the parameter is passed with 2 digits precision to the SMU
        def the_floor(a, digits=0):
            return np.true_divide(np.floor(a * 10 ** digits), 10 ** digits)

        nplc_found = the_floor(nplc_found,2)

        return nplc_found

    def load_data_points(self, datapoints):
        """
        load datapoints
        :param datapoints:
        :return:
        """
        if datapoints is []:
            logging.error('K2450: Data points empty')
        else:
            # check if bigger than 299995 samples (upper limit for the K2450), with two extra points and safety
            if len(self._datapoints) >= 299995:
                logging.warning('K2450: too many data points. Cropped to 299995!')
                datapoints = datapoints[:299995]

            self._datapoints = datapoints

    def _find_source_range(self, max_current):
        """
        Find the correct source (current) range, assures that a valid range is passed
        :param max_current
        :return: None in case of overrange
        """
        current_source_ranges = [10e-9, 100e-9, 1e-6, 10e-6, 100e-6, 1e-3, 10e-3, 100e-3, 1]
        found_range = None
        for source_range in reversed(current_source_ranges):
            if source_range >= max_current:
                found_range = source_range
        return found_range

    def _find_meas_range(self, max_expected_voltage):
        """
        Find the correct measurement (voltage) range, assures that a valid range is passed
        :param max_expected_voltage
        :return: None in case of overrange
        """
        voltage_measure_ranges = [0.02, 0.2, 2, 20, 200]
        found_range = None
        for measure_range in reversed(voltage_measure_ranges):
            if measure_range >= max_expected_voltage:
                found_range = measure_range
        return found_range

    def _find_protect_level(self, desired_protect_level):
        """
        Find the correct protect level, assures that a valid value is passed
        :param desired_protect_level
        :return: None in case of underrange
        """
        protect_levels = [2, 5, 10, 20, 40, 60, 80, 100, 120, 140, 160, 180]
        found_level = None
        for protect_level in protect_levels:
            if protect_level <= desired_protect_level:
                found_level = protect_level
        return found_level

    def get_linefreq(self):
        """
        get line frequency (50 or 60 Hz)
        :return:
        """
        self._inst.write("print(localnode.linefreq)")
        return int(self._inst.read())

    def _beep_error(self):
        if self.config.beep is True:
            self._inst.write("beeper.beep(0.08, 131)")  # C3
            self._inst.write("delay(0.08)")
            self._inst.write("beeper.beep(0.16, 131)")

    def _beep_start(self):
        if self.config.beep is True:
            self._inst.write("beeper.beep(0.08, 523)")  # C5
            self._inst.write("delay(0.25)")

    def _beep_end_ok(self):
        if self.config.beep is True:
            self._inst.write("beeper.beep(0.08, 262)")  # C4
            self._inst.write("beeper.beep(0.08, 523)")  # C5
            self._inst.write("beeper.beep(0.08, 659)")  # E5

    def _run_error_cleanup(self):
        self._inst.write("smu.source.output = smu.OFF")
        self._result_voltages = []
        self._result_currents = []
        self._result_timestamps = []
        self._beep_error()

    def run_sequence(self, simulate = False):
        """
        Run.
        * Makes a trigger timer
        * loads the values into a settings list
        * makes a trigger model depending on uvlo settings
        :param load_only: if True, it only loads the values, then exits before running
        :return:
        """
        self._run_warnings = 0

        logging.info('K2450 RUN: Run sequence started')

        self._beep_start()

        if self.config.auto_meas_range is False:
            # find correct measurement range (if not correctly given)
            meas_range = self._find_meas_range(self.config.meas_range)
            if meas_range is None:
                logging.error('K2450 RUN: Sanity check - Measurement range could not be matched!')
                self._run_error_cleanup()
                return False
            logging.info('K2450 RUN: Measurement range set to %0.2f V' % meas_range)
        else:
            logging.info('K2450 RUN: Auto Measurement range')

        if self.config.protect_enable is True:
            protect_voltage = self._find_protect_level(self.config.protect_voltage)
            if protect_voltage is None:
                logging.error('K2450 RUN: Sanity check - Protect level could not be matched!')
                self._run_error_cleanup()
                return False
            logging.info('K2450 RUN: Protect level set to %0.2f V' % protect_voltage)
            protect_voltage_string = "smu.source.protect.level = smu.PROTECT_%dV" % protect_voltage
        else:
            protect_voltage_string = "smu.source.protect.level = smu.PROTECT_NONE"

        if len(self._datapoints) == 0:
            logging.error('K2450 RUN: Sanity check - datapoints empty')
            self._run_error_cleanup()
            return False

        if self.config.auto_source_range is True:
            # list comprehension absolute of the loaded values
            source_range = self._find_source_range(max([abs(point) for point in self._datapoints]))
        else:
            source_range = self._find_source_range(self.config.source_range)

        if source_range is None:
            logging.error('K2450 RUN: seq sanity check: source range not found or unmatched!')
            self._run_error_cleanup()
            return False
        logging.info('K2450 Source: Current source range set to %0.2e' % source_range)

        if self.config.time_step < 0.002:
            logging.warning('K2450 RUN: seq sanity check: timestep too small')
            self._run_warnings += 1

        measure_time, source_delay = self._calc_timing(source_range)
        if measure_time is False:
            logging.error('K2450 RUN: Measure time calculation failed!')
            self._run_error_cleanup()
            return False

        if self.config.auto_nplc is False:
            nplc = self.config.nplc
        else:
            nplc = self._calc_autonplc(measure_time)

        # calculate minimum time step
        min_time_step = (1 / self._linefreq) * nplc + source_delay
        if self.config.auto_zero is True:
            min_meas_time = min_time_step * 2
        logging.info('K2450 RUN: Minimum time step is %0.2f ms' % (min_time_step * 1000))

        if min_time_step > self.config.time_step:
            logging.warning('K2450 RUN: Minumum time step is %0.2f times bigger than the time step setting!' % (min_time_step / self.config.time_step))
            if self.config.assure_timing is True:
                # if assure_timing is True the run will abort if a timing error is suspected
                logging.error('K2450 RUN: Timing check: Halted!')
                return False

        # ==========================================

        logging.info('K2450 RUN: create config list')

        self._inst.write("smu.source.configlist.create('"'SOURCE_LIST'"')")
        self._inst.write("smu.source.offmode = smu.OFFMODE_HIGHZ")
        self._inst.write("smu.source.func = smu.FUNC_DC_CURRENT")
        self._inst.write("smu.source.range = %0.2e" % source_range)

        if self.config.auto_delay is False:
            self._inst.write("smu.source.autodelay = smu.OFF")
            self._inst.write("smu.source.delay = %0.4f" % self.config.manual_delay)
        else:
            self._inst.write("smu.source.autodelay = smu.ON")

        self._inst.write(protect_voltage_string)
        self._inst.write("smu.source.vlimit.level = %0.2f" % self.config.limit_voltage)
        self._inst.write("smu.source.readback = smu.OFF")
        self._inst.write("smu.source.level = 0")
        self._inst.write("smu.source.configlist.store('"'SOURCE_LIST'"')")

        logging.info('K2450 RUN: populating config list')

        for value in self._datapoints:
            self._inst.write("smu.source.level = %.6e" % value)
            self._inst.write("smu.source.configlist.store('"'SOURCE_LIST'"')")

        self._inst.write("smu.source.level = 0") # last data point
        self._inst.write("smu.source.configlist.store('"'SOURCE_LIST'"')")

        # meas config list of one value - using same measure settings for all source levels
        self._inst.write("smu.measure.configlist.create('"'MEAS_LIST'"')")
        self._inst.write("smu.measure.func = smu.FUNC_DC_VOLTAGE")
        if self.config.auto_meas_range is False:
            self._inst.write("smu.measure.range = %0.2e" % meas_range)

        self._inst.write("smu.measure.nplc = %0.2f" % nplc)

        if self.config.four_wire is False:
            self._inst.write("smu.measure.sense = smu.SENSE_2WIRE")
        else:
            self._inst.write("smu.measure.sense = smu.SENSE_4WIRE")

        if self.config.auto_zero is False:
            self._inst.write("smu.measure.autozero.enable = smu.OFF")
        else:
            self._inst.write("smu.measure.autozero.enable = smu.ON")

        self._inst.write("smu.measure.configlist.store('"'MEAS_LIST'"')")

        logging.info('K2450 RUN: creating timer object')

        self._inst.write("trigger.timer[1].enable = 0")
        self._inst.write("trigger.timer[1].reset()")
        self._inst.write("trigger.timer[1].clear()")
        self._inst.write("trigger.timer[1].delay = %0.6f" % self.config.time_step)
        self._inst.write("trigger.timer[1].count = 0")
        self._inst.write("trigger.timer[1].start.stimulus = trigger.EVENT_NOTIFY1")  # see block 5
        self._inst.write("trigger.timer[1].start.generate = trigger.OFF")
        self._inst.write("trigger.timer[1].enable = 1")

        logging.info('K2450 RUN: setting up trigger blocks')

        off_delay = 0.5

        # see documentation for explanation of the trigger models
        self._inst.write("trigger.model.load('"'Empty'"')")
        self._inst.write("trigger.model.setblock(1, trigger.BLOCK_BUFFER_CLEAR, defbuffer1)")
        self._inst.write("trigger.model.setblock(2, trigger.BLOCK_SOURCE_OUTPUT, smu.ON)")
        self._inst.write("trigger.model.setblock(3, trigger.BLOCK_CONFIG_RECALL, '"'SOURCE_LIST'"', 1, '"'MEAS_LIST'"', 1)")
        self._inst.write("trigger.model.setblock(4, trigger.BLOCK_DELAY_CONSTANT, %0.4f)" % self.config.initial_delay)
        self._inst.write("trigger.model.setblock(5, trigger.BLOCK_NOTIFY, trigger.EVENT_NOTIFY1)")  # starts the timer
        self._inst.write("trigger.model.setblock(6, trigger.BLOCK_WAIT, trigger.EVENT_TIMER1)")
        self._inst.write("trigger.model.setblock(7, trigger.BLOCK_CONFIG_NEXT, '"'SOURCE_LIST'"')")
        self._inst.write("trigger.model.setblock(8, trigger.BLOCK_MEASURE, defbuffer1, 1)")
        if self.config.uvlo_enable is False:
            self._inst.write("trigger.model.setblock(9, trigger.BLOCK_BRANCH_COUNTER, %d, 6)" % len(self._datapoints))
            self._inst.write("trigger.model.setblock(10, trigger.BLOCK_CONFIG_NEXT, '"'SOURCE_LIST'"')")
            self._inst.write("trigger.model.setblock(11, trigger.BLOCK_DELAY_CONSTANT, %0.4f)" % off_delay)
            self._inst.write("trigger.model.setblock(12, trigger.BLOCK_SOURCE_OUTPUT, smu.OFF)")
            self._inst.write("trigger.model.setblock(13, trigger.BLOCK_BRANCH_ALWAYS, 0)")
        else:
            # configure a uvlo measurement trigger model
            logging.info('K2450 RUN: setting up extra trigger blocks for UVLO')
            self._inst.write("trigger.model.setblock(9, trigger.BLOCK_BRANCH_LIMIT_CONSTANT, trigger.LIMIT_BELOW, %0.2f,1, 15)" % self.config.uvlo_voltage)
            self._inst.write("trigger.model.setblock(10, trigger.BLOCK_BRANCH_COUNTER, %d, 6)" % len(self._datapoints))
            self._inst.write("trigger.model.setblock(11, trigger.BLOCK_CONFIG_NEXT, '"'SOURCE_LIST'"')")
            self._inst.write("trigger.model.setblock(12, trigger.BLOCK_DELAY_CONSTANT, %0.4f)" % off_delay)
            self._inst.write("trigger.model.setblock(13, trigger.BLOCK_SOURCE_OUTPUT, smu.OFF)")
            self._inst.write("trigger.model.setblock(14, trigger.BLOCK_BRANCH_ALWAYS, 0)")
            self._inst.write("trigger.model.setblock(15, trigger.BLOCK_LOG_EVENT, trigger.LOG_WARN1, '"'UVLO tripped!'"')")
            self._inst.write("trigger.model.setblock(16, trigger.BLOCK_BRANCH_ALWAYS, 13)")
        if self.config.auto_zero is not False:
            self._inst.write("smu.measure.autozero.once()")

        # calculate timeout
        run_length = self.config.time_step * len(self._datapoints)
        timeout = run_length + self.config.initial_delay + off_delay + 1
        logging.info('K2450 RUN: timeout set to %0.3f s' % timeout)

        # return if "simulation only"
        if simulate:
            logging.info('K2450 RUN: Break (Simulation run)')
            self._beep_end_ok()
            return self._run_warnings

        logging.info('K2450 RUN: run trigger model')
        self._inst.write("trigger.model.initiate()")

        # check if trigger model completed
        logging.info('K2450 RUN: poll for end of trigger model ...')

        runtime = 0.0
        while True:
            time.sleep(0.5)
            runtime += 0.5
            if runtime > timeout:
                logging.error('K2450 RUN: poll timeout!')
                self._run_error_cleanup()
                return False
            self._inst.write("print(trigger.model.state())")
            response = self._inst.read()
            if "trigger.STATE_IDLE" in response:
                logging.info('K2450 RUN: idle detected after %0.2f s' % runtime)
                break

        logging.info('K2450 RUN: retrieve measurements')
        self._result_voltages = self._inst.query_ascii_values("printbuffer(1, defbuffer1.n, defbuffer1.readings)",
                                                     container=np.array, separator=',', converter='f')

        self._result_currents = self._inst.query_ascii_values("printbuffer(1, defbuffer1.n, defbuffer1.sourcevalues)",
                                                 container=np.array, separator=',', converter='f')

        self._result_timestamps = self._inst.query_ascii_values("printbuffer(1, defbuffer1.n, defbuffer1.relativetimestamps)",
                                                  container=np.array, separator=',', converter='f')

        logging.info('K2450 RUN: PWL data length: %0.3f s' % run_length)
        retrieved_length = max(self._result_timestamps)
        logging.info('K2450 RUN: retrieved data length: %0.3f s' % retrieved_length)

        # check if shorter (maybe UVLO trip)
        if retrieved_length < run_length * 0.99:  # 1% tolerance allowed
            self._run_warnings += 1
            if self.config.uvlo_enable is False:
                logging.warning('K2450 RUN: received data << PWL data!')
            else:
                logging.warning('K2450 RUN: received data << PWL data, check for UVLO Message on Keithley!')

        # check if longer, maybe settings are wrong
        if retrieved_length > run_length * 1.01:  # 1% allowed
            self._run_warnings += 1
            logging.warning('K2450 RUN: received data >> PWL data, check timestep, (auto)delay, autozero and NLPC settings!')
        self._beep_end_ok()

        # that's it!
        return self._run_warnings

    def return_results(self):
        if not self.results_valid():
            logging.warning('K2450: Results empty')
            return None
        else:
            results = {'voltages': self._result_voltages, 'currents': self._result_currents, 'timestamps': self._result_timestamps}
            return results

    def results_valid(self):
        if (len(self._result_voltages) == 0) or (len(self._result_currents) == 0) or (
                len(self._result_timestamps) == 0):
            return False
        else:
            return True


if __name__ == '__main__':
    import logging
    logging.info = print  # temporarily redirect logging into Terminal

    from PWL_Parser import PWL_parser

    K2450_SL = K2450_ArbCurrentSource("USB0::0x05E6::0x2450::04425317::0::INSTR")

    K2450_SL.config.four_wire = True  # you can set the individual config elements manually
    K2450_SL.config.load_file('default.ini')  # or you can load a configuration file

    # load a pwl data file
    pwl_data = PWL_parser('test_pwl.txt', K2450_SL.config.time_step)

    # quick invert for load points (if needed)
    def Invert(lst):
        return [-i for i in lst]

    K2450_SL.load_data_points(Invert(pwl_data.values_discrete))
    status = K2450_SL.run_sequence(simulate=False)
    if status is False:
        print('Error occurred')
    else:
        print('Run finished with %d warnings' % status)

    results = K2450_SL.return_results()
    print(results['timestamps'])
    print(results['currents'])
    print(results['voltages'])

    del K2450_SL
