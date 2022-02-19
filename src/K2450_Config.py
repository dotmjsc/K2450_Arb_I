"""
A Configuration Class for the Keithley 2450 sequenced load
written by markus(a)schrodt.at
LICENSE: GPL-3.0-or-later
"""

import configparser
import logging


class K2450_Config(object):
    def __init__(self):
        self.visa_address = ""
        self.file_name = ""
        self.time_step = 0.1
        self.invert = False
        self.auto_zero = False
        self.auto_delay = True
        self.manual_delay = 0.001
        self.uvlo_enable = False
        self.uvlo_voltage = 0.1
        self.protect_voltage = 2
        self.protect_enable = True
        self.limit_voltage = 5
        self.source_range = 1
        self.auto_source_range = True
        self.four_wire = False
        self.meas_range = 200
        self.auto_meas_range = False
        self.nplc = 0.01
        self.auto_nplc = True
        self.beep = False
        self.assure_timing = False
        self.initial_delay = 1
        self._read_warnings = 0

    def save_file(self, filename):
        config = configparser.ConfigParser()
        config['INTERFACE']= {'visa address':  self.visa_address}

        config['FILE'] = {'file name':  self.file_name,
                          'time step sec':  self.time_step,
                          'invert':  self.invert}

        config['SOURCE'] = {'auto zero': self.auto_zero,
                            'auto delay': self.auto_delay,
                            'manual delay sec': self.manual_delay,
                            'uvlo enable': self.uvlo_enable,
                            'uvlo voltage': self.uvlo_voltage,
                            'protect voltage': self.protect_voltage,
                            'protect enable': self.protect_enable,
                            'limit voltage': self.limit_voltage,
                            'source range': self.source_range,
                            'auto source range': self.auto_source_range}

        config['MEASURE'] = {'four wire': self.four_wire,
                             'measurement range': self.meas_range,
                             'auto measurement range': self.auto_meas_range,
                             'nplc': self.nplc,
                             'auto nplc': self.auto_nplc,
                             'initial delay': self.initial_delay}

        config['MISC'] = {'beep': self.beep,
                          'assure timing': self.assure_timing}

        with open(filename, 'w') as configfile:
            config.write(configfile)

    def make_protect_string(self,value):
        if value is None:
            return 'None'
        else:
            return str(value)

    def load_file(self, filename):
        config = configparser.ConfigParser()
        try:
            config.read(filename)
            self._read_warnings = 0

            try:
                self.visa_address = config['INTERFACE'].get('visa address', fallback=self.visa_address)
            except:
                self._read_warnings += 1

            try:
                self.file_name = config['FILE'].get('file name', fallback=self.file_name)
            except:
                self._read_warnings += 1

            try:
                self.time_step = config['FILE'].getfloat('time step sec', fallback=self.time_step)
            except:
                self._read_warnings += 1

            try:
                self.invert = config['FILE'].getboolean('invert', fallback=self.invert)
            except:
                self._read_warnings += 1

            try:
                self.auto_zero = config['SOURCE'].getboolean('auto zero', fallback=self.auto_zero)
            except:
                self._read_warnings += 1

            try:
                self.auto_delay = config['SOURCE'].getboolean('auto delay', fallback=self.auto_delay)
            except:
                self._read_warnings += 1

            try:
                self.manual_delay = config['SOURCE'].getfloat('manual delay sec', fallback=self.manual_delay)
            except:
                self._read_warnings += 1

            try:
                self.uvlo_enable = config['SOURCE'].getboolean('uvlo enable', fallback=self.uvlo_enable)
            except:
                self._read_warnings += 1

            try:
                self.uvlo_voltage = config['SOURCE'].getfloat('uvlo voltage', fallback=self.uvlo_voltage)
            except:
                self._read_warnings += 1

            try:
                self.protect_voltage = config['SOURCE'].getfloat('protect voltage', fallback=self.protect_voltage)
            except:
                self._read_warnings += 1

            try:
                self.protect_enable = config['SOURCE'].getboolean('protect enable', fallback=self.protect_enable)
            except:
                self._read_warnings += 1

            try:
                self.limit_voltage = config['SOURCE'].getfloat('limit voltage', fallback=self.limit_voltage)
            except:
                self._read_warnings += 1

            try:
                self.four_wire = config['MEASURE'].getboolean('four wire', fallback=self.four_wire)
            except:
                self._read_warnings += 1

            try:
                self.meas_range = config['MEASURE'].getfloat('measurement range', fallback=self.meas_range)
            except:
                self._read_warnings += 1

            try:
                self.auto_meas_range = config['MEASURE'].getboolean('auto measurement range', fallback=self.auto_meas_range)
            except:
                self._read_warnings += 1

            try:
                self.source_range = config['SOURCE'].getfloat('source range', fallback=self.source_range)
            except:
                self._read_warnings += 1

            try:
                self.auto_source_range = config['SOURCE'].getboolean('auto source range', fallback=self.auto_source_range)
            except:
                self._read_warnings += 1

            try:
                self.nplc = config['SOURCE'].getfloat('nplc', fallback=self.nplc)
            except:
                self._read_warnings += 1

            try:
                self.auto_nplc = config['MEASURE'].getboolean('auto nplc', fallback=self.auto_nplc)
            except:
                self._read_warnings += 1

            try:
                self.initial_delay = config['MEASURE'].getfloat('initial delay', fallback=self.initial_delay)
            except:
                self._read_warnings += 1

            try:
                self.beep = config['MISC'].getboolean('beep', fallback=self.beep)
            except:
                self._read_warnings += 1

            try:
                self.assure_timing = config['MISC'].getboolean('check timing', fallback=self.assure_timing)
            except:
                self._read_warnings += 1

            logging.info('K2450 Cfg: config read')
            if self._read_warnings > 0:
                logging.warning('K2450 Cfg: %d read error(s)' % self._read_warnings)

        except:
            logging.error('K2450 Cfg: could not read config')


if __name__ == '__main__':
    smu_cfg = K2450_Config()
    smu_cfg.load_file('test.ini')
    print(smu_cfg.visa_address)
    smu_cfg.save_file('test2.ini')